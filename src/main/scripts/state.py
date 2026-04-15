"""
Core state and per-tick logic for Spidey Senses.

Ported from SpideySensesClient.java + ThreatTracker.java. All module-level
definitions share Python's __main__ namespace with the mixin scripts, so
camera_fov.py / lightmap.py / level_renderer.py can reference `envelope`,
`fov_envelope`, `run_world_sense_effect` by bare name.
"""

import java
import jarray
import polyglot

from elide.minecraft import mixin  # noqa: F401 — keeps elide/minecraft importable

# GraalPy's `PFloat.fitsInFloat(d)` returns true only when (double)(float)d == d.
# Most Python floats (64-bit) lose precision on float32 narrowing, so Java-float
# boundaries (farr[i] = v, state.floatField = v, return-value of a float-returning
# mixin) reject them outright. `register_interop_behavior` doesn't help — the
# native PFloat trait dispatches first on built-ins and before subclasses too.
#
# Workaround: pre-narrow each value through a Java round-trip. `.floatValue()`
# on a boxed Double returns a Java `float` primitive; when it crosses back to
# Python it's a Python `float` whose value is already exactly representable in
# 32-bit float — so every later fitsInFloat check succeeds.
_JavaFloat = java.type("java.lang.Float")


def jf(v):
    """Round `v` to the nearest 32-bit-representable double.

    Goes via String because `Float.parseFloat(str)` does the narrowing
    inside the JVM — no Python float ever crosses the fitsInFloat check.
    The returned Java float widens back to a Python float whose value
    is already at float32 granularity, so later assignments pass."""
    return _JavaFloat.parseFloat(str(v))

# --- Java type handles (looked up once, reused) ---
Minecraft          = java.type("net.minecraft.client.Minecraft")
Identifier         = java.type("net.minecraft.resources.Identifier")
LevelTargetBundle  = java.type("net.minecraft.client.renderer.LevelTargetBundle")
GpuBuffer          = java.type("com.mojang.blaze3d.buffers.GpuBuffer")
RenderSystem       = java.type("com.mojang.blaze3d.systems.RenderSystem")
Matrix4f           = java.type("org.joml.Matrix4f")
ByteBuffer         = java.type("java.nio.ByteBuffer")
FloatBuffer        = java.type("java.nio.FloatBuffer")
_FloatArrayType    = java.type("float[]")
# _JavaFloat defined above next to the jf() helper.
ByteOrder          = java.type("java.nio.ByteOrder")
Enemy              = java.type("net.minecraft.world.entity.monster.Enemy")
SpideySensesClient = java.type("com.example.spideysenses.SpideySensesClient")

# --- Constants (mirror the Java versions) ---
MOD_ID                 = "spidey-senses"
DETECTION_RADIUS       = 16.0
DETECTION_RADIUS_SQR   = DETECTION_RADIUS * DETECTION_RADIUS
TRIGGER_THRESHOLD      = 0.40
REARM_THRESHOLD        = 0.20
EFFECT_DURATION_TICKS  = 100
HOLD_FRACTION          = 0.20
COOLDOWN_TICKS         = 600
MAX_CHROMATIC_DISTORT  = 3.2
SENSE_EDGE_SOFTNESS    = 3.0
MAX_SHARPEN_AMOUNT     = 0.30
MAX_ZOOM_BLUR          = 0.0
COS_HALF_FOV           = 0.5

CHROMATIC_EFFECT   = Identifier.fromNamespaceAndPath(MOD_ID, "chromatic")
SENSE_WORLD_EFFECT = Identifier.fromNamespaceAndPath(MOD_ID, "sense_world")

# --- Mutable state (kept at module level so it persists across calls) ---
_threat         = 0.0
_trigger_ticks  = -1
_cooldown_ticks = 0
_armed          = True
_effect_applied = False


def prime():
    """No-op called once at mod init to force the module to be eval'd,
    so its globals are available when mixin scripts later fire."""
    return None


# ---------------- Threat tracking (ports ThreatTracker.java) ----------------

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

    closest_sqr = float("inf")
    for entity in level.entitiesForRendering():
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


# ---------------- Trigger state machine ----------------

def _advance_trigger():
    global _trigger_ticks, _armed, _cooldown_ticks

    if _threat < REARM_THRESHOLD:
        _armed = True

    # Cooldown is currently disabled (mirrors the Java commented-out block).
    # if _cooldown_ticks > 0:
    #     _cooldown_ticks -= 1

    if _armed and _threat >= TRIGGER_THRESHOLD and _trigger_ticks < 0:
        _trigger_ticks = 0
        _armed = False
        # _cooldown_ticks = COOLDOWN_TICKS

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
    if _trigger_ticks < 0:
        return 0.0
    progress = (_trigger_ticks + sub_tick) / EFFECT_DURATION_TICKS
    if progress >= 1.0:
        return 0.0
    peak = 0.25
    if progress < peak:
        return _smoothstep(progress / peak)
    return 1.0 - _smoothstep((progress - peak) / (1.0 - peak))


# ---------------- Post-effect activation ----------------

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


# ---------------- Uniform pushing ----------------

_JavaSystem = java.type("java.lang.System")


def _log(msg):
    _JavaSystem.err.println("[spidey-wf] " + str(msg))


def _fill_bytebuffer_with_floats(byte_buffer, values):
    """Writes `values` (Python floats) as 32-bit IEEE-754 little-endian
    into `byte_buffer` at offset 0 via a Java float[] + FloatBuffer view.
    Each value is pre-narrowed via jf() so the setArrayElement check passes."""
    n = len(values)
    farr = _FloatArrayType(n)
    for i, v in enumerate(values):
        farr[i] = jf(v)
    byte_buffer.order(ByteOrder.LITTLE_ENDIAN).asFloatBuffer().put(farr)


def _write_floats(uniforms_map, key, values):
    buf = uniforms_map.get(key)
    if buf is None:
        return
    byte_count = len(values) * 4
    if (buf.usage() & GpuBuffer.USAGE_COPY_DST) == 0:
        # Upgrade path: allocate new buffer with COPY_DST and seed with values.
        size = int(buf.size())
        initial = ByteBuffer.allocateDirect(size)
        _fill_bytebuffer_with_floats(initial, values)
        initial.rewind()
        replacement = SpideySensesClient.upgradeBuffer(buf, MOD_ID + "-" + key, initial)
        uniforms_map.put(key, replacement)
        return
    # Fast path: buffer already COPY_DST, just write.
    bb = ByteBuffer.allocateDirect(byte_count)
    _fill_bytebuffer_with_floats(bb, values)
    bb.rewind()
    RenderSystem.getDevice().createCommandEncoder().writeToBuffer(
        buf.slice(0, byte_count), bb
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
    # Matrix4f(Matrix4fc) copy ctor fails through GraalPy foreign-object
    # dispatch ("invalid instantiation"). `.set(m)` on a default-constructed
    # matrix takes the same interface arg and works.
    view = Matrix4f().set(camera.viewRotationMatrix).translate(
        jf(-pos.x), jf(-pos.y), jf(-pos.z)
    )
    inv_view_proj = Matrix4f().set(camera.projectionMatrix).mul(view).invert()

    # Column-major, matching how the shader reads mat4. Avoid get(FloatBuffer):
    # GraalPy dispatches that through JOML's unsafe direct-memory path and
    # segfaults on a bad address.
    m = [
        inv_view_proj.m00(), inv_view_proj.m01(), inv_view_proj.m02(), inv_view_proj.m03(),
        inv_view_proj.m10(), inv_view_proj.m11(), inv_view_proj.m12(), inv_view_proj.m13(),
        inv_view_proj.m20(), inv_view_proj.m21(), inv_view_proj.m22(), inv_view_proj.m23(),
        inv_view_proj.m30(), inv_view_proj.m31(), inv_view_proj.m32(), inv_view_proj.m33(),
    ]

    sharpen = MAX_SHARPEN_AMOUNT * env
    zoom_blur = MAX_ZOOM_BLUR * fov_envelope(0.0)

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
        if u.containsKey("ZoomBlurConfig"):
            _write_floats(u, "ZoomBlurConfig", [zoom_blur, 0.0, 0.0, 0.0])


def run_world_sense_effect(allocator, camera):
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


# ---------------- Tick entry ----------------

def on_client_tick(client):
    _threat_tick(client)
    _advance_trigger()
    _update_post_effect(client)
    _push_chromatic_uniforms(client)
