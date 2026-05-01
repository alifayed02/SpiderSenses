"""Corner tethering – horizontal loop around nearest block (C key)."""

import math

TETHER_RANGE = 24.0
TETHER_SPEED = 1.85

_tether_active   = False
_tether_anchor   = None
_tether_length   = 0.0
_tether_dir      = 1
_tether_y        = 0.0
_tether_prev_key = False


def _try_tether(client):
    global _tether_active, _tether_anchor, _tether_length, _tether_dir, _tether_y
    player = client.player
    level  = client.level
    if player is None or level is None:
        return

    center_y = float(player.getY()) + float(player.getBbHeight()) / 2.0
    origin = Vec3(float(player.getX()), center_y, float(player.getZ()))

    best_hit  = None
    best_dist = TETHER_RANGE + 1.0

    for deg in range(0, 360, 5):
        rad = math.radians(deg)
        dx = math.cos(rad)
        dz = math.sin(rad)
        end = origin.add(dx * TETHER_RANGE, 0.0, dz * TETHER_RANGE)
        hit = level.clip(ClipContext(origin, end, ClipBlock.COLLIDER, ClipFluid.NONE, player))
        if hit.getType() == HitType.BLOCK:
            dist = float(origin.distanceTo(hit.getLocation()))
            if dist < best_dist:
                best_hit = hit.getLocation()
                best_dist = dist

    if best_hit is None:
        return

    _tether_anchor = Vec3(float(best_hit.x), center_y, float(best_hit.z))
    _tether_length = best_dist
    _tether_y = center_y - float(player.getBbHeight()) / 2.0
    _tether_active = True

    vel = player.getDeltaMovement()
    rx = float(player.getX()) - float(_tether_anchor.x)
    rz = float(player.getZ()) - float(_tether_anchor.z)
    cross = rx * float(vel.z) - rz * float(vel.x)
    if abs(cross) < 1.0e-4:
        look = player.getViewVector(1.0)
        cross = rx * float(look.z) - rz * float(look.x)
    _tether_dir = 1 if cross >= 0 else -1

    Logger.info("[tether] ATTACHED at ({},{}) r={} dir={}",
                str(round(float(_tether_anchor.x), 1)),
                str(round(float(_tether_anchor.z), 1)),
                str(round(_tether_length, 1)),
                str(_tether_dir))


def _tick_tether(player):
    global _tether_active, _tether_anchor

    ax = float(_tether_anchor.x)
    az = float(_tether_anchor.z)
    px = float(player.getX())
    pz = float(player.getZ())

    dx = px - ax
    dz = pz - az
    dist = (dx * dx + dz * dz) ** 0.5

    if dist < 0.1:
        _tether_active = False
        _tether_anchor = None
        return

    rx = dx / dist
    rz = dz / dist

    tx = -rz * _tether_dir
    tz = rx * _tether_dir

    vel = player.getDeltaMovement()
    cur_tangent = float(vel.x) * tx + float(vel.z) * tz
    speed = max(TETHER_SPEED, cur_tangent)
    player.setDeltaMovement(Vec3(tx * speed, 0.08, tz * speed))

    overshoot = dist - _tether_length
    if abs(overshoot) > 0.01:
        player.move(MoverType.SELF, Vec3(-rx * overshoot, 0.0, -rz * overshoot))

    dy = _tether_y - float(player.getY())
    if abs(dy) > 0.01:
        player.move(MoverType.SELF, Vec3(0.0, dy, 0.0))

    player.fallDistance = float32(0.0)


def _detach_tether():
    global _tether_active, _tether_anchor
    Logger.info("[tether] DETACHED")
    _tether_active = False
    _tether_anchor = None


def tether_tick(client, player):
    global _tether_prev_key, _tether_active

    tether_down = InputConstants.isKeyDown(Minecraft.getInstance().getWindow(), GLFW_KEY_C)
    tether_just_pressed = tether_down and not _tether_prev_key
    _tether_prev_key = tether_down

    if _tether_active:
        if not tether_down:
            _detach_tether()
        else:
            _tick_tether(player)
    elif tether_just_pressed and not _attached and not _zip_active:
        _try_tether(client)


def tether_reset_keys():
    global _tether_prev_key
    _tether_prev_key = False


def tether_render(player, sub, cam):
    if not _tether_active or _tether_anchor is None:
        return
    hx, hy, hz = _get_hand_pos(player, sub)
    sx = float(hx - cam.x)
    sy = float(hy - cam.y)
    sz = float(hz - cam.z)
    ex = float(_tether_anchor.x - cam.x)
    ey = float(_tether_anchor.y - cam.y)
    ez = float(_tether_anchor.z - cam.z)
    _draw_strand(sx, sy, sz, ex, ey, ez, 1.0, 255)
