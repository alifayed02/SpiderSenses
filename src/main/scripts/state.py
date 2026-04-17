"""State, threat tracking, envelope curves, and per-tick logic.

Module-level definitions are shared with sibling mixin scripts via the
polyglot context's single global namespace, so camera_fov.py,
lightmap.py, and level_renderer.py can reference `envelope`,
`fov_envelope`, and `run_world_sense_effect` by bare name.
"""

import java

_JavaFloat = java.type("java.lang.Float")


def jf(v):
    """Narrow a Python double to a 32-bit-representable double.

    GraalPy rejects assignment of a Python 64-bit float into a Java
    32-bit float slot unless the value round-trips losslessly through
    float32. Routing through `Float.parseFloat(str)` performs the
    narrowing inside the JVM and returns a value that passes the
    check at every later Java-float boundary.
    """
    return _JavaFloat.parseFloat(str(v))


Minecraft          = java.type("net.minecraft.client.Minecraft")
Identifier         = java.type("net.minecraft.resources.Identifier")
LevelTargetBundle  = java.type("net.minecraft.client.renderer.LevelTargetBundle")
GpuBuffer          = java.type("com.mojang.blaze3d.buffers.GpuBuffer")
RenderSystem       = java.type("com.mojang.blaze3d.systems.RenderSystem")
Matrix4f           = java.type("org.joml.Matrix4f")
ByteBuffer         = java.type("java.nio.ByteBuffer")
ByteOrder          = java.type("java.nio.ByteOrder")
Enemy              = java.type("net.minecraft.world.entity.monster.Enemy")
SpideySensesClient = java.type("com.example.spideysenses.SpideySensesClient")
_FloatArrayType    = java.type("float[]")

MOD_ID                = SpideySensesClient.MOD_ID
DETECTION_RADIUS      = 16.0
DETECTION_RADIUS_SQR  = DETECTION_RADIUS * DETECTION_RADIUS
TRIGGER_THRESHOLD     = 0.40
REARM_THRESHOLD       = 0.20
EFFECT_DURATION_TICKS = 100
HOLD_FRACTION         = 0.20
COOLDOWN_TICKS        = 600
MAX_CHROMATIC_DISTORT = 3.2
SENSE_EDGE_SOFTNESS   = 3.0
MAX_SHARPEN_AMOUNT    = 0.30
MAX_FOV_GAIN          = 0.12
COS_HALF_FOV          = 0.5

CHROMATIC_EFFECT   = Identifier.fromNamespaceAndPath(MOD_ID, "chromatic")
SENSE_WORLD_EFFECT = Identifier.fromNamespaceAndPath(MOD_ID, "sense_world")

_threat         = 0.0
_trigger_ticks  = -1
_cooldown_ticks = 0
_armed          = True
_effect_applied = False


def prime():
    """Forces the module to evaluate, seeding shared state for mixin scripts."""
    return None


def _decay_threat():
    global _threat
    _threat *= 0.9
    if _threat < 0.001:
        _threat = 0.0


def _threat_tick(client):
    global _threat
    player = client.player
    level = client.level
    if player is None or level is None or client.isPaused():
        _decay_threat()
        return

    eye_pos = player.getEyePosition()
    view_vec = player.getViewVector(1.0)
    search_box = player.getBoundingBox().inflate(DETECTION_RADIUS)

    closest_sqr = float("inf")
    for entity in level.getEntities(player, search_box):
        if not isinstance(entity, Enemy):
            continue
        if not entity.isAlive():
            continue
        delta = entity.getEyePosition().subtract(eye_pos)
        length = delta.length()
        if length < 1.0e-6:
            continue
        dot = (delta.x * view_vec.x + delta.y * view_vec.y + delta.z * view_vec.z) / length
        if dot > COS_HALF_FOV:
            continue
        dist_sqr = entity.distanceToSqr(player)
        if dist_sqr < closest_sqr:
            closest_sqr = dist_sqr

    if closest_sqr >= DETECTION_RADIUS_SQR:
        target = 0.0
    else:
        target = 1.0 - (closest_sqr ** 0.5) / DETECTION_RADIUS

    smoothing = 0.25 if target > _threat else 0.08
    _threat = _threat + (target - _threat) * smoothing


def _advance_trigger():
    global _trigger_ticks, _armed, _cooldown_ticks

    if _threat < REARM_THRESHOLD:
        _armed = True

    if _cooldown_ticks > 0:
        _cooldown_ticks -= 1

    if _armed and _threat >= TRIGGER_THRESHOLD and _trigger_ticks < 0 and _cooldown_ticks == 0:
        _trigger_ticks = 0
        _armed = False
        _cooldown_ticks = COOLDOWN_TICKS

    if _trigger_ticks >= 0:
        _trigger_ticks += 1
        if _trigger_ticks >= EFFECT_DURATION_TICKS:
            _trigger_ticks = -1


def effect_active():
    return _trigger_ticks >= 0


def _clamp01(t):
    return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)


def _smoothstep(t):
    t = _clamp01(t)
    return t * t * (3.0 - 2.0 * t)


def envelope(sub_tick):
    """Rise / hold / fall curve over EFFECT_DURATION_TICKS."""
    if _trigger_ticks < 0:
        return 0.0
    progress = (_trigger_ticks + sub_tick) / EFFECT_DURATION_TICKS
    if progress >= 1.0:
        return 0.0
    rise_end = 0.15
    hold_end = rise_end + HOLD_FRACTION
    if progress < rise_end:
        return _smoothstep(progress / rise_end)
    if progress < hold_end:
        return 1.0
    return 1.0 - _smoothstep((progress - hold_end) / (1.0 - hold_end))


def fov_envelope(sub_tick):
    """Single-peak curve for the FOV warp."""
    if _trigger_ticks < 0:
        return 0.0
    progress = (_trigger_ticks + sub_tick) / EFFECT_DURATION_TICKS
    if progress >= 1.0:
        return 0.0
    peak = 0.25
    if progress < peak:
        return _smoothstep(progress / peak)
    return 1.0 - _smoothstep((progress - peak) / (1.0 - peak))


def _update_post_effect(client):
    global _effect_applied
    renderer = client.gameRenderer
    if renderer is None:
        return
    should_apply = effect_active()
    if should_apply and not _effect_applied:
        renderer.spideysenses_setPostEffect(CHROMATIC_EFFECT)
        _effect_applied = True
    elif not should_apply and _effect_applied:
        if CHROMATIC_EFFECT.equals(renderer.currentPostEffect()):
            renderer.clearPostEffect()
        _effect_applied = False


# Per-uniform-key reusable scratch: (java float[], direct ByteBuffer, FloatBuffer view).
# Steady-state writes hit this cache instead of allocating fresh native + view objects per tick.
_write_cache = {}


def _write_floats(uniforms_map, key, values):
    """Write `values` into the named uniform buffer, upgrading it to
    COPY_DST on first use (vanilla UBOs are allocated without the flag)."""
    buf = uniforms_map.get(key)
    if buf is None:
        return
    n = len(values)

    cached = _write_cache.get(key)
    if cached is None or len(cached[0]) != n:
        farr = _FloatArrayType(n)
        bb = ByteBuffer.allocateDirect(n * 4).order(ByteOrder.LITTLE_ENDIAN)
        cached = (farr, bb, bb.asFloatBuffer())
        _write_cache[key] = cached
    farr, bb, fb = cached

    for i, v in enumerate(values):
        farr[i] = jf(v)

    if (buf.usage() & GpuBuffer.USAGE_COPY_DST) == 0:
        # One-time upgrade: vanilla UBOs lack COPY_DST, so allocate a fresh
        # GpuBuffer with the flag, seeded with our values padded to UBO size.
        size = int(buf.size())
        initial = ByteBuffer.allocateDirect(size).order(ByteOrder.LITTLE_ENDIAN)
        initial.asFloatBuffer().put(farr)
        initial.rewind()
        replacement = SpideySensesClient.upgradeBuffer(buf, MOD_ID + "-" + key, initial)
        uniforms_map.put(key, replacement)
        return

    fb.rewind()
    fb.put(farr)
    bb.rewind()
    RenderSystem.getDevice().createCommandEncoder().writeToBuffer(
        buf.slice(0, n * 4), bb
    )


def _push_chromatic_uniforms(client):
    if not effect_active():
        return
    distort = MAX_CHROMATIC_DISTORT * envelope(0.0)
    chain = client.getShaderManager().getPostChain(
        CHROMATIC_EFFECT, LevelTargetBundle.MAIN_TARGETS
    )
    if chain is None:
        return
    for pass_ in chain.spideysenses_passes():
        uniforms_map = pass_.spideysenses_customUniforms()
        if uniforms_map.containsKey("AberrationConfig"):
            _write_floats(uniforms_map, "AberrationConfig", [distort])


def _push_sense_world_uniforms(chain, camera):
    env = envelope(0.0)
    max_radius = camera.depthFar if camera.depthFar > 0.0 else 512.0
    radius = max_radius * env
    strength = env

    pos = camera.pos
    view = Matrix4f().set(camera.viewRotationMatrix).translate(
        jf(-pos.x), jf(-pos.y), jf(-pos.z)
    )
    inv_view_proj = Matrix4f().set(camera.projectionMatrix).mul(view).invert()

    m = [
        inv_view_proj.m00(), inv_view_proj.m01(), inv_view_proj.m02(), inv_view_proj.m03(),
        inv_view_proj.m10(), inv_view_proj.m11(), inv_view_proj.m12(), inv_view_proj.m13(),
        inv_view_proj.m20(), inv_view_proj.m21(), inv_view_proj.m22(), inv_view_proj.m23(),
        inv_view_proj.m30(), inv_view_proj.m31(), inv_view_proj.m32(), inv_view_proj.m33(),
    ]

    sharpen = MAX_SHARPEN_AMOUNT * env

    sense_uniforms = [
        radius, SENSE_EDGE_SOFTNESS, strength, 0.0,
        float(pos.x), float(pos.y), float(pos.z), 0.0,
    ] + m

    for pass_ in chain.spideysenses_passes():
        u = pass_.spideysenses_customUniforms()
        if u.containsKey("SenseConfig"):
            _write_floats(u, "SenseConfig", sense_uniforms)
        if u.containsKey("SharpenConfig"):
            _write_floats(u, "SharpenConfig", [sharpen])


def run_world_sense_effect(allocator, camera):
    """Run the world-space sense post-effect chain. Called from the
    LevelRenderer.renderLevel TAIL mixin."""
    if not effect_active():
        return
    if (
        camera is None
        or camera.projectionMatrix is None
        or camera.viewRotationMatrix is None
        or camera.pos is None
    ):
        return
    client = Minecraft.getInstance()
    chain = client.getShaderManager().getPostChain(
        SENSE_WORLD_EFFECT, LevelTargetBundle.MAIN_TARGETS
    )
    if chain is None:
        return
    _push_sense_world_uniforms(chain, camera)
    chain.process(client.getMainRenderTarget(), allocator)


def on_client_tick(client):
    _threat_tick(client)
    _advance_trigger()
    _update_post_effect(client)
    _push_chromatic_uniforms(client)
