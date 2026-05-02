"""Wall running and climbing – auto wall-run mid-air, R to climb."""

import math

WALL_DETECT_RANGE = 3.0
WALL_CLIMB_DETECT = 1.0
WALL_MOVE_SPEED = 0.15
WALL_JUMP_HORIZONTAL = 0.7
WALL_JUMP_VERTICAL = 0.5
WALL_RUN_GRAVITY = 0.008
WALL_RUN_SLIDE_MAX = -0.15
WALL_RUN_MAX_TICKS = 60
WALL_STICK_DIST = 0.3
WALL_CLIMB_NO_CONTACT_MAX = 5
WALL_CLIMB_STICK = 0.15
WALL_CLIMB_SCAN = 1.5

GLFW_KEY_R = 82

_wall_active = False
_wall_mode = None
_wall_normal = None
_wall_ticks = 0
_wall_prev_key = False
_wall_prev_jump = False
_wall_cooldown = 0
_wall_run_y_speed = 0.0
_wall_no_contact = 0
_wall_anim_pos = 0.0
_wall_anim_speed = 0.0


def _player_facing_xz(player):
    """Player's horizontal facing direction in world space."""
    yaw_rad = math.radians(float(player.getYRot(1.0)))
    return -math.sin(yaw_rad), math.cos(yaw_rad)


def _player_center(player):
    """Vec3 at the player's vertical mid-point."""
    cy = float(player.getY()) + float(player.getBbHeight()) / 2.0
    return Vec3(float(player.getX()), cy, float(player.getZ()))


def _other_web_active():
    """Whether another web ability is currently in use."""
    try:
        return _attached or _zip_active or _tether_active
    except NameError:
        return False


def _find_wall(player, level, max_range):
    origin = _player_center(player)

    best_hit = None
    best_dist = max_range + 1.0
    best_nx = 0.0
    best_nz = 0.0

    for deg in range(0, 360, 10):
        rad = math.radians(deg)
        end = origin.add(math.cos(rad) * max_range, 0.0, math.sin(rad) * max_range)
        hit = level.clip(ClipContext(origin, end, ClipBlock.COLLIDER, ClipFluid.NONE, player))
        if hit.getType() != HitType.BLOCK:
            continue
        face = hit.getDirection()
        fnx = float(int(face.getStepX()))
        fny = float(int(face.getStepY()))
        fnz = float(int(face.getStepZ()))
        if fny != 0.0 or (fnx == 0.0 and fnz == 0.0):
            continue
        dist = float(origin.distanceTo(hit.getLocation()))
        if dist < best_dist:
            best_hit = hit.getLocation()
            best_dist = dist
            best_nx = fnx
            best_nz = fnz

    if best_hit is None:
        return None
    return (best_hit, best_nx, best_nz)


def _attach_wall(player, hit_loc, nx, nz, mode):
    global _wall_active, _wall_normal, _wall_mode
    global _wall_ticks, _wall_run_y_speed, _wall_no_contact

    _wall_normal = (nx, nz)
    _wall_mode = mode
    _wall_ticks = 0
    _wall_run_y_speed = 0.0
    _wall_no_contact = 0
    _wall_active = True

    if mode == 'run':
        player.setDeltaMovement(Vec3(0.0, 0.0, 0.0))

    Logger.info("[wall] {} at ({},{}) normal=({},{})",
                "CLIMB" if mode == 'climb' else "RUN",
                str(round(float(hit_loc.x), 1)),
                str(round(float(hit_loc.z), 1)),
                str(round(nx, 2)), str(round(nz, 2)))


def _detach_wall(reason):
    global _wall_active, _wall_normal, _wall_mode
    Logger.info("[wall] DETACHED reason={} mode={} ticks={}", reason, str(_wall_mode), str(_wall_ticks))
    _wall_active = False
    _wall_normal = None
    _wall_mode = None


def _wall_jump(player):
    global _wall_cooldown

    level = Minecraft.getInstance().level
    if _wall_mode == 'climb' and level is not None:
        result = _find_wall(player, level, WALL_DETECT_RANGE)
        if result is not None:
            nx, nz = result[1], result[2]
        else:
            nx, nz = _wall_normal if _wall_normal is not None else (0.0, 0.0)
    elif _wall_normal is not None:
        nx, nz = _wall_normal
    else:
        nx, nz = 0.0, 0.0

    kp = player.input.keyPresses
    fwd = 1.0 if kp.forward() else (-1.0 if kp.backward() else 0.0)
    strafe = 1.0 if kp.left() else (-1.0 if kp.right() else 0.0)

    if abs(fwd) > 0.01 or abs(strafe) > 0.01:
        fx, fz = _player_facing_xz(player)
        ix = fx * fwd + fz * strafe
        iz = fz * fwd + (-fx) * strafe
        mag = (ix * ix + iz * iz) ** 0.5
        if mag > 1e-4:
            ix /= mag
            iz /= mag
        jx = nx * 0.6 + ix * 0.4
        jz = nz * 0.6 + iz * 0.4
    else:
        jx = nx
        jz = nz

    hmag = (jx * jx + jz * jz) ** 0.5
    if hmag > 1e-4:
        jx /= hmag
        jz /= hmag

    player.setDeltaMovement(Vec3(jx * WALL_JUMP_HORIZONTAL, WALL_JUMP_VERTICAL, jz * WALL_JUMP_HORIZONTAL))
    player.fallDistance = float32(0.0)
    _detach_wall("jump")
    _wall_cooldown = 5


def _get_wall_velocity(player):
    """Project WASD input onto the wall surface using the look direction (run mode only)."""
    nx, nz = _wall_normal

    look = player.getViewVector(1.0)
    lx, ly, lz = float(look.x), float(look.y), float(look.z)

    dot = lx * nx + lz * nz
    px = lx - dot * nx
    py = ly
    pz = lz - dot * nz
    mag = (px * px + py * py + pz * pz) ** 0.5

    if mag < 0.01:
        fx, fy, fz = 0.0, 1.0, 0.0
    else:
        fx, fy, fz = px / mag, py / mag, pz / mag

    sx = -nz * fy
    sy = nz * fx - nx * fz
    sz = nx * fy
    smag = (sx * sx + sy * sy + sz * sz) ** 0.5
    if smag > 1e-4:
        sx /= smag
        sy /= smag
        sz /= smag

    kp = player.input.keyPresses
    fwd_in = 1.0 if kp.forward() else (-1.0 if kp.backward() else 0.0)
    str_in = 1.0 if kp.left() else (-1.0 if kp.right() else 0.0)

    mx = fx * fwd_in + sx * str_in
    my = fy * fwd_in + sy * str_in
    mz = fz * fwd_in + sz * str_in

    mmag = (mx * mx + my * my + mz * mz) ** 0.5
    if mmag > 1.0:
        mx /= mmag
        my /= mmag
        mz /= mmag

    return mx, my, mz


def _scan_closest_wall(player, level):
    """Per-tick 4-cardinal raycast to find the closest wall face. Returns (nx, nz) or None."""
    origin = _player_center(player)
    best_dist = WALL_CLIMB_SCAN + 0.1
    best = None

    for cnx, cnz in ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0)):
        end = origin.add(-cnx * WALL_CLIMB_SCAN, 0.0, -cnz * WALL_CLIMB_SCAN)
        hit = level.clip(ClipContext(origin, end, ClipBlock.COLLIDER, ClipFluid.NONE, player))
        if hit.getType() == HitType.BLOCK:
            d = float(origin.distanceTo(hit.getLocation()))
            if d < best_dist:
                best_dist = d
                best = (cnx, cnz)
    return best


def _advance_climb_anim(player):
    """Drive walkAnimationPos/Speed from full 3D velocity so vertical motion animates."""
    global _wall_anim_pos, _wall_anim_speed
    vel = player.getDeltaMovement()
    speed_3d = (float(vel.x) ** 2 + float(vel.y) ** 2 + float(vel.z) ** 2) ** 0.5
    target = min(speed_3d * 4.0, 1.0)
    _wall_anim_speed += (target - _wall_anim_speed) * 0.4
    _wall_anim_pos += _wall_anim_speed


def _tick_wall_climb(player):
    """Spiders 2.0-inspired climbing: per-tick closest-face scan + sticking force."""
    global _wall_no_contact, _wall_normal

    level = Minecraft.getInstance().level
    closest = _scan_closest_wall(player, level)
    if closest is None:
        _wall_no_contact += 1
        if _wall_no_contact > WALL_CLIMB_NO_CONTACT_MAX:
            _detach_wall("no_wall")
            return
    else:
        _wall_no_contact = 0
        _wall_normal = closest
        nx, nz = closest
        player.move(MoverType.SELF, Vec3(-nx * WALL_CLIMB_STICK, 0.0, -nz * WALL_CLIMB_STICK))

    kp = player.input.keyPresses
    w, s, a, d = kp.forward(), kp.backward(), kp.left(), kp.right()

    if w or s or a or d:
        speed = 0.2
        fx, fz = _player_facing_xz(player)
        ix, iy, iz = 0.0, 0.0, 0.0
        if a:
            ix += fz
            iz += -fx
        if d:
            ix += -fz
            iz += fx
        if w:
            iy += 1.0
        if s:
            iy -= 1.0

        mag = (ix * ix + iy * iy + iz * iz) ** 0.5
        if mag > 1e-6:
            ix /= mag
            iy /= mag
            iz /= mag

        player.setDeltaMovement(Vec3(ix * speed, iy * speed, iz * speed))
    else:
        player.setDeltaMovement(Vec3(0.0, 0.0, 0.0))

    player.fallDistance = float32(0.0)
    _advance_climb_anim(player)


def _tick_wall_run(player):
    """Wall-run mode: raycast-based with look-relative WASD."""
    global _wall_run_y_speed

    if _wall_ticks > WALL_RUN_MAX_TICKS:
        _detach_wall("max_ticks")
        return
    if player.onGround() and _wall_ticks > 3:
        _detach_wall("ground")
        return

    nx, nz = _wall_normal
    origin = _player_center(player)
    check_end = origin.add(-nx * WALL_DETECT_RANGE, 0.0, -nz * WALL_DETECT_RANGE)

    level = Minecraft.getInstance().level
    hit = level.clip(ClipContext(origin, check_end, ClipBlock.COLLIDER, ClipFluid.NONE, player))
    if hit.getType() != HitType.BLOCK:
        _detach_wall("no_wall")
        return

    wall_dist = float(origin.distanceTo(hit.getLocation()))
    correction = WALL_STICK_DIST - wall_dist
    if abs(correction) > 0.01:
        player.move(MoverType.SELF, Vec3(nx * correction, 0.0, nz * correction))

    mx, my, mz = _get_wall_velocity(player)
    speed = WALL_MOVE_SPEED
    _wall_run_y_speed -= WALL_RUN_GRAVITY
    if _wall_run_y_speed < WALL_RUN_SLIDE_MAX:
        _wall_run_y_speed = WALL_RUN_SLIDE_MAX
    vy = 0.08 + my * speed + _wall_run_y_speed
    player.setDeltaMovement(Vec3(mx * speed, vy, mz * speed))
    player.fallDistance = float32(0.0)


def _handle_attached(player, r_just_pressed):
    global _wall_mode, _wall_run_y_speed, _wall_ticks, _wall_prev_jump

    if r_just_pressed:
        if _wall_mode == 'run':
            _wall_mode = 'climb'
            _wall_run_y_speed = 0.0
            _wall_ticks = 0
            Logger.info("[wall] SWITCHED to CLIMB")
        else:
            _detach_wall("r_key")
            return

    kp = player.input.keyPresses
    jump_down = kp.jump()
    jump_just_pressed = jump_down and not _wall_prev_jump
    _wall_prev_jump = jump_down

    if jump_just_pressed:
        _wall_jump(player)
        return

    _wall_ticks += 1
    if _wall_mode == 'climb':
        _tick_wall_climb(player)
    else:
        _tick_wall_run(player)


def _handle_detached(client, player, r_just_pressed):
    global _wall_prev_jump
    _wall_prev_jump = False

    if _other_web_active():
        return
    level = client.level
    if level is None:
        return

    if r_just_pressed:
        result = _find_wall(player, level, WALL_CLIMB_DETECT)
        if result is not None:
            _attach_wall(player, result[0], result[1], result[2], 'climb')
        return

    if (not player.onGround() and player.horizontalCollision
            and _wall_cooldown == 0):
        vel = player.getDeltaMovement()
        h_speed = (float(vel.x) ** 2 + float(vel.z) ** 2) ** 0.5
        if h_speed >= 0.2:
            Logger.info("[wall] AUTO-RUN trigger: hSpeed={} vy={}",
                        str(round(h_speed, 3)), str(round(float(vel.y), 3)))
            result = _find_wall(player, level, WALL_DETECT_RANGE)
            if result is not None:
                _attach_wall(player, result[0], result[1], result[2], 'run')


def wall_tick(client, player):
    global _wall_prev_key, _wall_cooldown

    r_down = InputConstants.isKeyDown(Minecraft.getInstance().getWindow(), GLFW_KEY_R)
    r_just_pressed = r_down and not _wall_prev_key
    _wall_prev_key = r_down

    if _wall_cooldown > 0:
        _wall_cooldown -= 1

    if _wall_active:
        _handle_attached(player, r_just_pressed)
    else:
        _handle_detached(client, player, r_just_pressed)


def wall_reset_keys():
    global _wall_prev_key, _wall_prev_jump
    _wall_prev_key = False
    _wall_prev_jump = False
