"""Web swinging – input detection, raycasting, pendulum physics, and line rendering."""

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
Vec3         = java.type("net.minecraft.world.phys.Vec3")

WEB_ROPE_MIN         = 1.0
CONSTRAINT_STIFFNESS = 0.2

SEARCH_RANGE      = 48.0
SKYHOOK_FORWARD   = 20.0
SKYHOOK_HEIGHT    = 15.0
MIN_ANCHOR_HEIGHT = 2.0
SCORE_THRESHOLD   = 0.15
REUSE_PENALTY_DIST = 5.0

_YAWS    = [math.radians(a) for a in (-30, -15, 0, 15, 30)]
_PITCHES = [math.radians(a) for a in (10, 25, 40, 55, 70)]

WEB_SEGMENTS  = 24
WEB_HALF_WIDTH = 0.025
FULL_BRIGHT    = 15728880

_attached      = False
_anchor        = None
_last_anchor   = None
_rope_length   = 0.0
_prev_use      = False
_tension       = 0.0
_prev_tension  = 0.0
_rope_ticks    = 0
_in_ground     = False
_was_airborne  = False
_detached      = None


def prime():
    return None


def _search_direction(player):
    vel  = player.getDeltaMovement()
    look = player.getViewVector(1.0)
    vh   = vel.horizontalDistance()
    blend = min(1.0, vh / 0.3)
    if vh < 1.0e-4:
        hlen = (look.x ** 2 + look.z ** 2) ** 0.5
        return (look.x / hlen, look.z / hlen) if hlen > 1.0e-4 else (0.0, 1.0)
    vx = vel.x / vh
    vz = vel.z / vh
    sx = look.x * (1.0 - blend) + vx * blend
    sz = look.z * (1.0 - blend) + vz * blend
    sh = (sx * sx + sz * sz) ** 0.5
    if sh < 1.0e-4:
        return (vx, vz)
    return (sx / sh, sz / sh)


def _score_candidate(player_pos, player_vel, hit_pos):
    dx = hit_pos.x - player_pos.x
    dy = hit_pos.y - player_pos.y
    dz = hit_pos.z - player_pos.z
    dist = (dx * dx + dy * dy + dz * dz) ** 0.5

    if dy < MIN_ANCHOR_HEIGHT:
        return -1.0

    dist_score   = max(0.0, 1.0 - ((dist - 20.0) / 15.0) ** 2)
    height_score = max(0.0, 1.0 - ((dy - 14.0) / 10.0) ** 2)

    vel_h = player_vel.horizontalDistance()
    if vel_h > 0.1:
        horiz = (dx * dx + dz * dz) ** 0.5
        alignment = (player_vel.x * dx + player_vel.z * dz) / (vel_h * horiz) if horiz > 0.01 else 0.0
        vel_score = (alignment + 1.0) / 2.0
    else:
        vel_score = 0.5

    horiz = (dx * dx + dz * dz) ** 0.5
    arc_score = min(1.0, horiz / 10.0)

    score = dist_score * 0.20 + height_score * 0.25 + vel_score * 0.35 + arc_score * 0.20

    if _last_anchor is not None and hit_pos.distanceTo(_last_anchor) < REUSE_PENALTY_DIST:
        score *= 0.5

    return score


def _try_shoot(client):
    global _attached, _anchor, _rope_length, _tension, _prev_tension, _rope_ticks, _in_ground, _was_airborne
    player = client.player
    level  = client.level
    if player is None or level is None:
        return
    if not player.getMainHandItem().isEmpty():
        return

    pos = player.position()
    eye = player.getEyePosition()
    vel = player.getDeltaMovement()
    sx, sz = _search_direction(player)

    best_score = -1.0
    best_point = None

    for yaw in _YAWS:
        sin_y = math.sin(yaw)
        cos_y = math.cos(yaw)
        rx = sx * cos_y - sz * sin_y
        rz = sx * sin_y + sz * cos_y

        for pitch in _PITCHES:
            sin_p = math.sin(pitch)
            cos_p = math.cos(pitch)
            dx = rx * cos_p
            dy = sin_p
            dz = rz * cos_p

            end = eye.add(dx * SEARCH_RANGE, dy * SEARCH_RANGE, dz * SEARCH_RANGE)
            hit = level.clip(
                ClipContext(eye, end, ClipBlock.COLLIDER, ClipFluid.NONE, player)
            )
            if hit.getType() != HitType.BLOCK:
                continue

            score = _score_candidate(pos, vel, hit.getLocation())
            if score > best_score:
                best_score = score
                best_point = hit.getLocation()

    if best_score >= SCORE_THRESHOLD and best_point is not None:
        _anchor = best_point
        _in_ground = True
        Logger.info("[web] ATTACHED to block at ({},{},{}) score={} rope={}",
                     str(round(float(_anchor.x), 1)), str(round(float(_anchor.y), 1)), str(round(float(_anchor.z), 1)),
                     str(round(best_score, 3)), str(round(float(pos.distanceTo(_anchor)), 1)))
    else:
        _anchor = pos.add(sx * SKYHOOK_FORWARD, SKYHOOK_HEIGHT, sz * SKYHOOK_FORWARD)
        _in_ground = False
        Logger.info("[web] SKYHOOK at ({},{},{}) bestScore={}",
                     str(round(float(_anchor.x), 1)), str(round(float(_anchor.y), 1)), str(round(float(_anchor.z), 1)),
                     str(round(best_score, 3)))

    _rope_length = max(WEB_ROPE_MIN, pos.distanceTo(_anchor))
    _attached = True
    _tension = 0.0
    _prev_tension = 0.0
    _rope_ticks = 0
    _was_airborne = False


def _detach(player):
    global _attached, _anchor, _last_anchor, _rope_length, _detached
    global _tension, _prev_tension, _rope_ticks
    Logger.info("[web] DETACHED")
    _last_anchor = _anchor
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


def _restrict_motion(ax, ay, az, ex, ey, ez):
    dx = ax - ex
    dy = ay - ey
    dz = az - ez
    dist_sq = dx * dx + dy * dy + dz * dz
    rope = max(_rope_length, WEB_ROPE_MIN)
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

    v = _restrict_motion(ax, ay, az, px, py, pz)
    if v is None:
        return

    vx, vy, vz = v

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
            input_force = min(2.0, speed) / 12.0
            player.setDeltaMovement(vel.add(ix * input_force, 0.0, iz * input_force))

    player.move(MoverType.SELF, Vec3(vx, vy, vz))

    vel = player.getDeltaMovement()
    player.setDeltaMovement(vel.add(vx, vy, vz))

    vel = player.getDeltaMovement()
    v1 = _restrict_motion(ax, ay, az,
                          px + float(vel.x), py + float(vel.y), pz + float(vel.z))
    if v1 is not None:
        player.setDeltaMovement(player.getDeltaMovement().add(
            v1[0] - vx, v1[1] - vy, v1[2] - vz))

    vel = player.getDeltaMovement()
    if float(vel.y) >= 0 or vy >= 0 or (v1 is not None and vy - v1[1] >= 0):
        player.fallDistance = float32(0.0)


def render_web_line(level_renderer, camera, delta):
    if not _attached and _detached is None:
        return
    player = Minecraft.getInstance().player
    if player is None:
        return

    sub = float(delta.getGameTimeDeltaPartialTick(True))
    cam = camera.pos
    alpha = 255

    if _attached and _anchor is not None:
        pos = player.getPosition(sub)
        yaw = math.radians(float(player.getYRot(sub)))
        rx = -math.sin(yaw)
        rz =  math.cos(yaw)
        sx = float(pos.x + rx * 0.35 - cam.x)
        sy = float(float(pos.y) + float(player.getEyeHeight()) * 0.7 - cam.y)
        sz = float(pos.z + rz * 0.35 - cam.z)
        ex = float(_anchor.x - cam.x)
        ey = float(_anchor.y - cam.y)
        ez = float(_anchor.z - cam.z)
        t_interp = _prev_tension + (_tension - _prev_tension) * sub
    elif _detached is not None:
        r = _detached
        sx = float(r[0] - cam.x)
        sy = float(r[1] - cam.y)
        sz = float(r[2] - cam.z)
        ex = float((r[9] + (r[3] - r[9]) * sub) - cam.x)
        ey = float((r[10] + (r[4] - r[10]) * sub) - cam.y)
        ez = float((r[11] + (r[5] - r[11]) * sub) - cam.z)
        t_interp = r[14] + (r[13] - r[14]) * sub
        alpha = max(0, int(255 * (1.0 - (r[15] + sub) / 60.0)))
        if alpha <= 0:
            return
    else:
        return

    rdx = ex - sx
    rdy = ey - sy
    rdz = ez - sz
    rope_len = (rdx * rdx + rdy * rdy + rdz * rdz) ** 0.5
    if rope_len < 0.1:
        return

    rt = 1.0 - t_interp
    if rt < 0.001:
        segments = 1
    else:
        segments = WEB_SEGMENTS

    if sy > ey:
        mid_x = sx
        mid_y = sy + (ey - sy) * rt * 2.0
        mid_z = sz
    else:
        mid_x = ex
        mid_y = ey + (sy - ey) * rt * 2.0
        mid_z = ez

    hw = WEB_HALF_WIDTH

    mv = RenderSystem.getModelViewStack()
    mv.pushMatrix()
    mv.set(camera.viewRotationMatrix)

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

        builder.addVertex(float32(px - bx), float32(py - by), float32(pz - bz)).setColor(255, 255, 255, alpha).setLight(FULL_BRIGHT)
        builder.addVertex(float32(px + bx), float32(py + by), float32(pz + bz)).setColor(255, 255, 255, alpha).setLight(FULL_BRIGHT)

    mesh = builder.buildOrThrow()
    leash.draw(mesh)

    mv.popMatrix()


def web_tick(client):
    global _prev_use, _rope_length, _rope_ticks, _tension, _prev_tension, _was_airborne
    player = client.player
    if player is None or client.isPaused():
        _prev_use = False
        return

    _tick_detached(client)

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

        if _was_airborne and player.onGround() and _rope_ticks > 10:
            _ground_boost_detach(player)
            return

        _apply_pendulum(player)

        _prev_tension = _tension
        px = float(player.getX())
        py = float(player.getY()) + float(player.getBbHeight())
        pz = float(player.getZ())
        ax = float(_anchor.x)
        ay = float(_anchor.y)
        az = float(_anchor.z)
        length = ((ax - px) ** 2 + (ay - py) ** 2 + (az - pz) ** 2) ** 0.5
        if _in_ground:
            target = min((length + 1.0) / _rope_length, 1.0)
        else:
            target = 1.0
        _tension = _tension - (_tension - target) / 4.0

    elif just_pressed:
        _try_shoot(client)
