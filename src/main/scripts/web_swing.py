"""Web swinging – pendulum physics with rappel control."""

WEB_ROPE_MIN         = 1.0
CONSTRAINT_STIFFNESS = 0.2
SEARCH_RANGE         = 48.0

RAPPEL_RAMP    = 8.0
RAPPEL_SPEED   = 0.1
RAPPEL_MIN_LEN = 0.5

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


def swing_tick(client, player):
    global _prev_use, _rope_ticks, _tension, _prev_tension, _was_airborne

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


def swing_reset_keys():
    global _prev_use
    _prev_use = False


def swing_render(player, sub, cam):
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
        if alpha > 0:
            _draw_strand(sx, sy, sz, ex, ey, ez, t_interp, alpha)
