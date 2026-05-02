"""Web swinging – shared imports, swing mechanics, and ability orchestration."""

import java
import math

from elide import float32

Logger      = java.type("com.example.spideysenses.SpideySensesClient").LOGGER
Minecraft   = java.type("net.minecraft.client.Minecraft")
ClipContext = java.type("net.minecraft.world.level.ClipContext")
ClipBlock   = java.type("net.minecraft.world.level.ClipContext$Block")
ClipFluid   = java.type("net.minecraft.world.level.ClipContext$Fluid")
HitType     = java.type("net.minecraft.world.phys.HitResult$Type")
RenderTypes  = java.type("net.minecraft.client.renderer.rendertype.RenderTypes")
Tesselator   = java.type("com.mojang.blaze3d.vertex.Tesselator")
RenderSystem = java.type("com.mojang.blaze3d.systems.RenderSystem")
MoverType    = java.type("net.minecraft.world.entity.MoverType")
Vec3             = java.type("net.minecraft.world.phys.Vec3")
InputConstants   = java.type("com.mojang.blaze3d.platform.InputConstants")
GLFW_KEY_Z       = 90
GLFW_KEY_C       = 67

WEB_ROPE_MIN         = 1.0
CONSTRAINT_STIFFNESS = 0.2

SEARCH_RANGE      = 48.0

RAPPEL_RAMP     = 8.0
RAPPEL_SPEED    = 0.1
RAPPEL_MIN_LEN  = 0.5

WEB_SEGMENTS  = 24
WEB_HALF_WIDTH = 0.025
FULL_BRIGHT    = 15728880

_attached      = False
_anchor        = None
_rope_length   = 0.0
_prev_use      = False
_tension       = 0.0
_prev_tension  = 0.0
_rope_ticks    = 0
_in_ground     = False
_was_airborne  = False
_detached      = None

_rappel_timer      = 0.0
_rappel_prev_timer = 0.0
_rappel_direction  = 0

exec(open("src/main/scripts/web_zip.py").read())
exec(open("src/main/scripts/web_tether.py").read())
exec(open("src/main/scripts/web_wall_run.py").read())
exec(open("src/main/scripts/web_charge_jump.py").read())


def prime():
    return None


def _try_shoot(client):
    global _attached, _anchor, _rope_length, _tension, _prev_tension, _rope_ticks, _in_ground, _was_airborne
    player = client.player
    level  = client.level
    if player is None or level is None:
        return
    if not player.getMainHandItem().isEmpty():
        return

    eye  = player.getEyePosition()
    look = player.getViewVector(1.0)
    end  = eye.add(look.x * SEARCH_RANGE, look.y * SEARCH_RANGE, look.z * SEARCH_RANGE)
    hit  = level.clip(ClipContext(eye, end, ClipBlock.COLLIDER, ClipFluid.NONE, player))
    if hit.getType() != HitType.BLOCK:
        return

    _anchor = hit.getLocation()
    _in_ground = True
    attach_point = player.position().add(0.0, float(player.getBbHeight()), 0.0)
    _rope_length = max(WEB_ROPE_MIN, attach_point.distanceTo(_anchor))
    _attached = True
    _tension = 0.0
    _prev_tension = 0.0
    _rope_ticks = 0
    _was_airborne = False
    Logger.info("[web] ATTACHED at ({},{},{}) rope={}",
                str(round(float(_anchor.x), 1)), str(round(float(_anchor.y), 1)), str(round(float(_anchor.z), 1)),
                str(round(float(_rope_length), 1)))


def _detach(player):
    global _attached, _anchor, _rope_length, _detached
    global _tension, _prev_tension, _rope_ticks
    global _rappel_timer, _rappel_prev_timer, _rappel_direction
    Logger.info("[web] DETACHED")
    vel = player.getDeltaMovement()
    px, py, pz = float(player.getX()), float(player.getY()), float(player.getZ())
    _detached = [
        float(_anchor.x), float(_anchor.y), float(_anchor.z),
        px, py, pz,
        float(vel.x), float(vel.y), float(vel.z),
        px, py, pz,
        _rope_length, _tension, _tension, 0, _in_ground,
    ]
    _attached    = False
    _anchor      = None
    _rope_length = 0.0
    _tension     = 0.0
    _prev_tension = 0.0
    _rope_ticks  = 0
    _rappel_timer      = 0.0
    _rappel_prev_timer = 0.0
    _rappel_direction  = 0


def _ground_boost_detach(player):
    vel = player.getDeltaMovement()
    mx = float(vel.x)
    my = float(vel.y)
    mz = float(vel.z)
    pull = max(-1.0, min(1.0, (float(_anchor.y) - float(player.getY())) * 0.1))
    player.setDeltaMovement(Vec3(mx * 0.9 + mx, my * 0.9 + (my + pull), mz * 0.9 + mz))
    _detach(player)


def _tick_detached(client):
    global _detached
    if _detached is None:
        return
    r = _detached
    r[15] += 1
    if r[15] > 60:
        _detached = None
        return

    r[9]  = r[3]
    r[10] = r[4]
    r[11] = r[5]

    level  = client.level
    player = client.player
    if level is not None and player is not None:
        ep  = Vec3(r[3], r[4], r[5])
        nep = Vec3(r[3] + r[6], r[4] + r[7], r[5] + r[8])
        hit = level.clip(ClipContext(ep, nep, ClipBlock.COLLIDER, ClipFluid.NONE, player))
        if hit.getType() == HitType.BLOCK:
            r[6] *= -0.3
            r[7] *= -0.3
            r[8] *= -0.3

    r[6] *= 0.7
    r[7] *= 0.7
    r[8] *= 0.7
    r[7] -= 0.02

    r[3] += r[6]
    r[4] += r[7]
    r[5] += r[8]

    r[14] = r[13]
    dx = r[0] - r[3]
    dy = r[1] - r[4]
    dz = r[2] - r[5]
    length = (dx * dx + dy * dy + dz * dz) ** 0.5
    if r[16]:
        target = min((length + 1.0) / r[12], 1.0)
    else:
        target = 1.0
    r[13] = r[13] - (r[13] - target) / 4.0


def _restrict_motion(ax, ay, az, ex, ey, ez, eff_rope=None):
    dx = ax - ex
    dy = ay - ey
    dz = az - ez
    dist_sq = dx * dx + dy * dy + dz * dz
    rope = max(eff_rope if eff_rope is not None else _rope_length, WEB_ROPE_MIN)
    if dist_sq > rope * rope:
        dist = dist_sq ** 0.5
        overshoot = (dist - rope) * CONSTRAINT_STIFFNESS
        return (dx / dist * overshoot, dy / dist * overshoot, dz / dist * overshoot)
    return None


def _apply_pendulum(player):
    ax = float(_anchor.x)
    ay = float(_anchor.y)
    az = float(_anchor.z)
    px = float(player.getX())
    py = float(player.getY()) + float(player.getBbHeight())
    pz = float(player.getZ())

    eff_rope = max(_rope_length - _rappel_timer * float(player.getBbHeight()), RAPPEL_MIN_LEN)

    v = _restrict_motion(ax, ay, az, px, py, pz, eff_rope)
    if v is None:
        return

    vx, vy, vz = v

    steer_scale = 1.0 - _rappel_timer
    if steer_scale > 1.0e-4:
        vel = player.getDeltaMovement()
        speed = (float(vel.x) ** 2 + float(vel.y) ** 2 + float(vel.z) ** 2) ** 0.5
        move = player.input.getMoveVector()
        fwd = float(move.y)
        strafe = float(move.x)
        mag = (fwd * fwd + strafe * strafe) ** 0.5
        if mag >= 1.0e-4:
            if mag > 1.0:
                fwd /= mag
                strafe /= mag
            look = player.getViewVector(1.0)
            hlen = (look.x ** 2 + look.z ** 2) ** 0.5
            if hlen > 1.0e-4:
                fx = look.x / hlen
                fz = look.z / hlen
                ix = fx * fwd + fz * strafe
                iz = fz * fwd + (-fx) * strafe
                input_force = min(2.0, speed) / 12.0 * steer_scale
                player.setDeltaMovement(vel.add(ix * input_force, 0.0, iz * input_force))

    player.move(MoverType.SELF, Vec3(vx, vy, vz))

    vel = player.getDeltaMovement()
    player.setDeltaMovement(vel.add(vx, vy, vz))

    vel = player.getDeltaMovement()
    v1 = _restrict_motion(ax, ay, az,
                          px + float(vel.x), py + float(vel.y), pz + float(vel.z), eff_rope)
    if v1 is not None:
        player.setDeltaMovement(player.getDeltaMovement().add(
            v1[0] - vx, v1[1] - vy, v1[2] - vz))

    vel = player.getDeltaMovement()
    if float(vel.y) >= 0 or vy >= 0 or (v1 is not None and vy - v1[1] >= 0):
        player.fallDistance = float32(0.0)


def _tick_rappel(player):
    global _rappel_timer, _rappel_prev_timer, _rappel_direction, _rope_length

    _rappel_prev_timer = _rappel_timer

    sneaking = player.isShiftKeyDown()

    if sneaking:
        was = _rappel_timer
        _rappel_timer = min(1.0, _rappel_timer + 1.0 / RAPPEL_RAMP)
        if was == 0.0:
            Logger.info("[rappel] ENTERING")
        if _rappel_timer >= 1.0 and was < 1.0:
            Logger.info("[rappel] FULL  rope={}", str(round(_rope_length, 2)))
    else:
        was = _rappel_timer
        _rappel_timer = max(0.0, _rappel_timer - 1.0 / RAPPEL_RAMP)
        if was > 0.0 and _rappel_timer == 0.0:
            Logger.info("[rappel] EXITED")
        _rappel_direction = 0
        return

    if _rappel_timer >= 1.0:
        kp = player.input.keyPresses
        if kp.forward():
            _rappel_direction = 1
        elif kp.backward():
            _rappel_direction = -1
        else:
            _rappel_direction = 0
    else:
        _rappel_direction = 0

    min_rope = RAPPEL_MIN_LEN + _rappel_timer * float(player.getBbHeight())

    if _rappel_direction != 0:
        new_len = max(_rope_length - RAPPEL_SPEED * _rappel_direction, min_rope)
        if new_len != _rope_length:
            _rope_length = new_len
            Logger.info("[rappel] ADJUST dir={} rope={} eff={}",
                        str(_rappel_direction), str(round(_rope_length, 2)),
                        str(round(max(_rope_length - _rappel_timer * float(player.getBbHeight()), RAPPEL_MIN_LEN), 2)))
        else:
            _rappel_direction = 0


def _get_hand_pos(player, sub, side='right'):
    mc  = Minecraft.getInstance()
    pos = player.getPosition(sub)
    if mc.options.getCameraType().isFirstPerson():
        pitch = math.radians(float(player.getXRot(sub)))
        yaw   = math.radians(float(player.getYRot(sub)))
        ox = -0.3 if side == 'right' else 0.3
        oy, oz = -0.15, 0.4
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)
        ry   = oy * cos_p - oz * sin_p
        rz_r = oy * sin_p + oz * cos_p
        cos_y = math.cos(yaw)
        sin_y = math.sin(yaw)
        hx = ox * cos_y - rz_r * sin_y
        hz = ox * sin_y + rz_r * cos_y
        hy = ry
        return (float(pos.x) + hx, float(pos.y) + float(player.getEyeHeight()) + hy, float(pos.z) + hz)
    else:
        by = math.radians(float(player.yBodyRotO) + (float(player.yBodyRot) - float(player.yBodyRotO)) * sub)
        cos_by = math.cos(by)
        sin_by = math.sin(by)
        renderer = mc.getEntityRenderDispatcher().getRenderer(player)
        model    = renderer.getModel()
        if side == 'right':
            arm_pitch = float(model.rightArm.xRot)
        else:
            arm_pitch = float(model.leftArm.xRot)
        arm_len   = 10.0 / 16.0
        tip_down  = -arm_len * math.cos(arm_pitch)
        tip_fwd   = arm_len * math.sin(arm_pitch)
        sign = -1.0 if side == 'right' else 1.0
        return (
            float(pos.x) + sign * cos_by * 5.0 / 16.0 - sin_by * tip_fwd,
            float(pos.y) + 22.0 / 16.0 + tip_down,
            float(pos.z) + sign * sin_by * 5.0 / 16.0 + cos_by * tip_fwd,
        )


def _draw_strand(sx, sy, sz, ex, ey, ez, t_interp, alpha, cr=255, cg=255, cb=255):
    rdx = ex - sx
    rdy = ey - sy
    rdz = ez - sz
    rope_len = (rdx * rdx + rdy * rdy + rdz * rdz) ** 0.5
    if rope_len < 0.1:
        return

    rt = 1.0 - t_interp
    segments = 1 if rt < 0.001 else WEB_SEGMENTS

    if sy > ey:
        mid_x, mid_y, mid_z = sx, sy + (ey - sy) * rt * 2.0, sz
    else:
        mid_x, mid_y, mid_z = ex, ey + (sy - ey) * rt * 2.0, ez

    hw = WEB_HALF_WIDTH

    leash = RenderTypes.leash()
    builder = Tesselator.getInstance().begin(leash.mode(), leash.format())

    for i in range(segments + 1):
        t = i / segments
        u = 1.0 - t
        px = u * u * sx + 2.0 * u * t * mid_x + t * t * ex
        py = u * u * sy + 2.0 * u * t * mid_y + t * t * ey
        pz = u * u * sz + 2.0 * u * t * mid_z + t * t * ez

        bx = rdy * pz - rdz * py
        by = rdz * px - rdx * pz
        bz = rdx * py - rdy * px
        bl = (bx * bx + by * by + bz * bz) ** 0.5
        if bl < 1.0e-6:
            bx, by, bz = 0.0, hw, 0.0
        else:
            bx = bx / bl * hw
            by = by / bl * hw
            bz = bz / bl * hw

        builder.addVertex(float32(px - bx), float32(py - by), float32(pz - bz)).setColor(cr, cg, cb, alpha).setLight(FULL_BRIGHT)
        builder.addVertex(float32(px + bx), float32(py + by), float32(pz + bz)).setColor(cr, cg, cb, alpha).setLight(FULL_BRIGHT)

    mesh = builder.buildOrThrow()
    leash.draw(mesh)


def render_web_line(level_renderer, camera, delta):
    if not _attached and not _zip_active and not _tether_active and _detached is None:
        return
    player = Minecraft.getInstance().player
    if player is None:
        return

    sub = float(delta.getGameTimeDeltaPartialTick(True))
    cam = camera.pos

    mv = RenderSystem.getModelViewStack()
    mv.pushMatrix()
    mv.set(camera.viewRotationMatrix)

    if _attached and _anchor is not None:
        hx, hy, hz = _get_hand_pos(player, sub)
        sx = float(hx - cam.x)
        sy = float(hy - cam.y)
        sz = float(hz - cam.z)
        ex = float(_anchor.x - cam.x)
        ey = float(_anchor.y - cam.y)
        ez = float(_anchor.z - cam.z)
        t_interp = _prev_tension + (_tension - _prev_tension) * sub
        _draw_strand(sx, sy, sz, ex, ey, ez, t_interp, 255)
    else:
        zip_render(player, sub, cam)
        tether_render(player, sub, cam)
        if _detached is not None:
            r = _detached
            sx = float(r[0] - cam.x)
            sy = float(r[1] - cam.y)
            sz = float(r[2] - cam.z)
            ex = float((r[9] + (r[3] - r[9]) * sub) - cam.x)
            ey = float((r[10] + (r[4] - r[10]) * sub) - cam.y)
            ez = float((r[11] + (r[5] - r[11]) * sub) - cam.z)
            t_interp = r[14] + (r[13] - r[14]) * sub
            alpha = max(0, int(255 * (1.0 - (r[15] + sub) / 60.0)))
            if alpha > 0:
                _draw_strand(sx, sy, sz, ex, ey, ez, t_interp, alpha)

    mv.popMatrix()


def web_tick(client):
    global _prev_use, _rope_length, _rope_ticks, _tension, _prev_tension, _was_airborne
    player = client.player
    if player is None or client.isPaused():
        _prev_use = False
        zip_reset_keys()
        tether_reset_keys()
        wall_reset_keys()
        charge_jump_reset_keys()
        return

    _tick_detached(client)
    tether_tick(client, player)
    zip_tick(client, player)
    wall_tick(client, player)
    charge_jump_tick(client, player)

    use = client.options.keyUse.isDown()
    just_pressed  = use and not _prev_use
    just_released = not use and _prev_use
    _prev_use = use

    if _attached:
        _rope_ticks += 1

        if not player.onGround():
            _was_airborne = True

        if just_released:
            _detach(player)
            return

        if _rappel_timer > 0.0 and player.onGround():
            Logger.info("[rappel] LANDED — disconnecting")
            _detach(player)
            return

        if _was_airborne and player.onGround() and _rope_ticks > 10:
            _ground_boost_detach(player)
            return

        _tick_rappel(player)
        _apply_pendulum(player)

        _prev_tension = _tension
        px = float(player.getX())
        py = float(player.getY()) + float(player.getBbHeight())
        pz = float(player.getZ())
        ax = float(_anchor.x)
        ay = float(_anchor.y)
        az = float(_anchor.z)
        eff = max(_rope_length - _rappel_timer * float(player.getBbHeight()), RAPPEL_MIN_LEN)
        length = ((ax - px) ** 2 + (ay - py) ** 2 + (az - pz) ** 2) ** 0.5
        if _in_ground:
            target = min((length + 1.0) / eff, 1.0)
        else:
            target = 1.0
        _tension = _tension - (_tension - target) / 4.0

    elif just_pressed and not _zip_active and not _tether_active and not _wall_active:
        _try_shoot(client)
