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

WEB_ROPE_MIN     = 3.0
SWING_FORCE      = 0.065
SWING_PUMP_BONUS = 2.0

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

_attached     = False
_anchor       = None
_last_anchor  = None
_rope_length  = 0.0
_prev_use     = False


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
    global _attached, _anchor, _rope_length
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
        Logger.info("[web] ATTACHED to block at ({},{},{}) score={} rope={}",
                     str(round(float(_anchor.x), 1)), str(round(float(_anchor.y), 1)), str(round(float(_anchor.z), 1)),
                     str(round(best_score, 3)), str(round(float(pos.distanceTo(_anchor)), 1)))
    else:
        _anchor = pos.add(sx * SKYHOOK_FORWARD, SKYHOOK_HEIGHT, sz * SKYHOOK_FORWARD)
        Logger.info("[web] SKYHOOK at ({},{},{}) bestScore={}",
                     str(round(float(_anchor.x), 1)), str(round(float(_anchor.y), 1)), str(round(float(_anchor.z), 1)),
                     str(round(best_score, 3)))

    _rope_length = max(WEB_ROPE_MIN, pos.distanceTo(_anchor))
    _attached = True


def _detach():
    global _attached, _anchor, _last_anchor, _rope_length
    Logger.info("[web] DETACHED")
    _last_anchor = _anchor
    _attached    = False
    _anchor      = None
    _rope_length = 0.0


def _apply_swing_input(player, rx, ry, rz):
    move = player.input.getMoveVector()
    fwd    = float(move.y)
    strafe = float(move.x)
    if abs(fwd) < 0.01 and abs(strafe) < 0.01:
        return

    look = player.getViewVector(1.0)
    hlen = (look.x ** 2 + look.z ** 2) ** 0.5
    if hlen < 1.0e-4:
        return
    fx = look.x / hlen
    fz = look.z / hlen

    ix = fx * fwd + (-fz) * strafe
    iz = fz * fwd + fx * strafe

    dot_r = ix * rx + iz * rz
    tx = ix - dot_r * rx
    ty =    - dot_r * ry
    tz = iz - dot_r * rz
    tlen = (tx * tx + ty * ty + tz * tz) ** 0.5
    if tlen < 1.0e-4:
        return
    tx /= tlen
    ty /= tlen
    tz /= tlen

    force = SWING_FORCE
    vel = player.getDeltaMovement()
    if fwd > 0.0 and vel.y < 0.0 and player.getY() < _anchor.y:
        force *= SWING_PUMP_BONUS

    player.setDeltaMovement(vel.add(tx * force, ty * force, tz * force))


def _apply_pendulum(player):
    global _rope_length
    px = player.getX() - _anchor.x
    py = player.getY() - _anchor.y
    pz = player.getZ() - _anchor.z
    dist = (px * px + py * py + pz * pz) ** 0.5
    if dist < 1.0e-4:
        return

    rx, ry, rz = px / dist, py / dist, pz / dist

    _apply_swing_input(player, rx, ry, rz)

    vel = player.getDeltaMovement()
    if dist >= _rope_length:
        v_rad = vel.x * rx + vel.y * ry + vel.z * rz
        if v_rad > 0.0:
            vel = vel.subtract(v_rad * rx, v_rad * ry, v_rad * rz)
            player.setDeltaMovement(vel)

        player.setPos(
            _anchor.x + rx * _rope_length,
            _anchor.y + ry * _rope_length,
            _anchor.z + rz * _rope_length,
        )

    player.fallDistance = float32(0.0)


def render_web_line(level_renderer, camera, delta):
    if not _attached or _anchor is None:
        return
    player = Minecraft.getInstance().player
    if player is None:
        return

    sub = float(delta.getGameTimeDeltaPartialTick(True))
    cam = camera.pos
    pos = player.getPosition(sub)

    yaw = math.radians(float(player.getYRot(sub)))
    rx = -math.sin(yaw)
    rz =  math.cos(yaw)

    hand_x = pos.x + rx * 0.35
    hand_y = float(pos.y) + float(player.getEyeHeight()) * 0.7
    hand_z = pos.z + rz * 0.35

    sx = float(hand_x - cam.x)
    sy = float(hand_y - cam.y)
    sz = float(hand_z - cam.z)
    ex = float(_anchor.x - cam.x)
    ey = float(_anchor.y - cam.y)
    ez = float(_anchor.z - cam.z)

    rdx = ex - sx
    rdy = ey - sy
    rdz = ez - sz
    rope_len = (rdx * rdx + rdy * rdy + rdz * rdz) ** 0.5
    if rope_len < 0.1:
        return

    sag = min(1.5, rope_len * 0.03)
    hw = WEB_HALF_WIDTH

    mv = RenderSystem.getModelViewStack()
    mv.pushMatrix()
    mv.set(camera.viewRotationMatrix)

    leash = RenderTypes.leash()
    builder = Tesselator.getInstance().begin(leash.mode(), leash.format())

    for i in range(WEB_SEGMENTS + 1):
        t = i / WEB_SEGMENTS
        px = sx + rdx * t
        py = sy + rdy * t - sag * math.sin(t * math.pi)
        pz = sz + rdz * t

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

        builder.addVertex(float32(px - bx), float32(py - by), float32(pz - bz)).setColor(255, 255, 255, 255).setLight(FULL_BRIGHT)
        builder.addVertex(float32(px + bx), float32(py + by), float32(pz + bz)).setColor(255, 255, 255, 255).setLight(FULL_BRIGHT)

    mesh = builder.buildOrThrow()
    leash.draw(mesh)

    mv.popMatrix()


def web_tick(client):
    global _prev_use, _rope_length
    player = client.player
    if player is None or client.isPaused():
        _prev_use = False
        return

    use = client.options.keyUse.isDown()
    just_pressed  = use and not _prev_use
    just_released = not use and _prev_use
    _prev_use = use

    if _attached:
        if just_released:
            _detach()
            return
        if player.onGround():
            dist = player.position().distanceTo(_anchor)
            if dist > _rope_length:
                _rope_length = dist
        else:
            _apply_pendulum(player)
    elif just_pressed:
        _try_shoot(client)
