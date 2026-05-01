"""Web zip – dual-web pull toward blocks/entities (Z key)."""

import math

ZIP_RANGE       = 48.0
ZIP_COOLDOWN    = 20
ZIP_BLOCK_TICKS = 5
ZIP_BLOCK_SPEED = 1.5
ZIP_ENTITY_TICKS = 10
ZIP_ENTITY_SPEED = 1.5

_zip_active     = False
_zip_target     = None
_zip_entity     = None
_zip_ticks      = 0
_zip_cooldown   = 0
_zip_prev_key   = False
_zip_anchor_l   = None
_zip_anchor_r   = None
_zip_converging = True
_zip_holding    = False


def _try_zip(client):
    global _zip_active, _zip_target, _zip_entity, _zip_ticks
    global _zip_anchor_l, _zip_anchor_r, _zip_converging, _zip_holding
    player = client.player
    level  = client.level
    if player is None or level is None:
        return

    eye  = player.getEyePosition()
    look = player.getViewVector(1.0)
    end  = eye.add(look.x * ZIP_RANGE, look.y * ZIP_RANGE, look.z * ZIP_RANGE)

    block_hit  = level.clip(ClipContext(eye, end, ClipBlock.COLLIDER, ClipFluid.NONE, player))
    block_dist = ZIP_RANGE + 1.0
    if block_hit.getType() == HitType.BLOCK:
        block_dist = float(eye.distanceTo(block_hit.getLocation()))

    search_box  = player.getBoundingBox().expandTowards(
        look.x * ZIP_RANGE, look.y * ZIP_RANGE, look.z * ZIP_RANGE
    ).inflate(1.0)
    best_entity = None
    best_dist   = block_dist

    for entity in level.getEntities(player, search_box):
        if not entity.isAlive() or not entity.isPickable():
            continue
        bb  = entity.getBoundingBox().inflate(float(entity.getPickRadius()) + 0.3)
        clip = bb.clip(eye, end)
        if clip.isPresent():
            dist = float(eye.distanceTo(clip.get()))
            if dist < best_dist:
                best_entity = entity
                best_dist   = dist

    if best_entity is not None:
        _zip_target = best_entity.position().add(0, float(best_entity.getBbHeight()) / 2.0, 0)
        _zip_entity = best_entity
        _zip_anchor_l = _zip_target
        _zip_anchor_r = _zip_target
        _zip_converging = True
        _zip_holding = True
        _zip_active = True
        _zip_ticks  = 0
        Logger.info("[web] ZIP entity at ({},{},{})",
                    str(round(float(_zip_target.x), 1)),
                    str(round(float(_zip_target.y), 1)),
                    str(round(float(_zip_target.z), 1)))
    elif block_hit.getType() == HitType.BLOCK:
        _zip_target = block_hit.getLocation()
        _zip_entity = None
        _zip_anchor_l = _zip_target
        _zip_anchor_r = _zip_target
        _zip_converging = True
        _zip_holding = True
        _zip_active = True
        _zip_ticks  = 0
        Logger.info("[web] ZIP block at ({},{},{})",
                    str(round(float(_zip_target.x), 1)),
                    str(round(float(_zip_target.y), 1)),
                    str(round(float(_zip_target.z), 1)))
    else:
        yaw_rad = math.radians(float(player.getYRot(1.0)))
        best_l = None
        best_l_score = -1.0
        best_r = None
        best_r_score = -1.0

        for h_deg in list(range(-45, -3, 4)) + list(range(5, 46, 4)):
            for p_deg in range(-20, 21, 5):
                p_rad = math.radians(p_deg)
                ray_yaw = yaw_rad + math.radians(h_deg)
                dx = -math.sin(ray_yaw) * math.cos(p_rad)
                dy = -math.sin(p_rad)
                dz = math.cos(ray_yaw) * math.cos(p_rad)
                ray_end = eye.add(dx * ZIP_RANGE, dy * ZIP_RANGE, dz * ZIP_RANGE)
                hit = level.clip(ClipContext(eye, ray_end, ClipBlock.COLLIDER, ClipFluid.NONE, player))
                if hit.getType() != HitType.BLOCK:
                    continue
                dist = float(eye.distanceTo(hit.getLocation()))
                score = 0.45 * (dist / ZIP_RANGE) + 0.35 * (abs(h_deg) / 45.0) + 0.2 * ((20.0 - p_deg) / 40.0)
                if h_deg < 0 and score > best_l_score:
                    best_l = hit.getLocation()
                    best_l_score = score
                elif h_deg > 0 and score > best_r_score:
                    best_r = hit.getLocation()
                    best_r_score = score

        if best_l is not None and best_r is not None:
            _zip_anchor_l = best_l
            _zip_anchor_r = best_r
            mid_x = (float(_zip_anchor_l.x) + float(_zip_anchor_r.x)) / 2.0
            mid_y = (float(_zip_anchor_l.y) + float(_zip_anchor_r.y)) / 2.0
            mid_z = (float(_zip_anchor_l.z) + float(_zip_anchor_r.z)) / 2.0
            _zip_target = Vec3(mid_x, mid_y, mid_z)
            _zip_entity = None
            _zip_converging = False
            _zip_holding = True
            _zip_active = True
            _zip_ticks = 0
            Logger.info("[web] ZIP diverge L=({},{},{}) R=({},{},{})",
                        str(round(float(_zip_anchor_l.x), 1)),
                        str(round(float(_zip_anchor_l.y), 1)),
                        str(round(float(_zip_anchor_l.z), 1)),
                        str(round(float(_zip_anchor_r.x), 1)),
                        str(round(float(_zip_anchor_r.y), 1)),
                        str(round(float(_zip_anchor_r.z), 1)))


def _tick_zip(player):
    global _zip_active, _zip_target, _zip_entity, _zip_ticks, _zip_cooldown
    global _zip_anchor_l, _zip_anchor_r
    if not _zip_active:
        return

    _zip_ticks += 1
    speed = ZIP_ENTITY_SPEED if _zip_entity is not None else ZIP_BLOCK_SPEED

    if _zip_entity is not None and _zip_entity.isAlive():
        _zip_target = _zip_entity.position().add(0, float(_zip_entity.getBbHeight()) / 2.0, 0)
        _zip_anchor_l = _zip_target
        _zip_anchor_r = _zip_target

    if _zip_ticks > 2 and (player.horizontalCollision or player.verticalCollision):
        if _zip_entity is not None and _zip_entity.isAlive():
            player.attack(_zip_entity)
        _zip_active   = False
        _zip_target   = None
        _zip_entity   = None
        _zip_anchor_l = None
        _zip_anchor_r = None
        _zip_cooldown = ZIP_COOLDOWN
        player.setDeltaMovement(Vec3(0.0, 0.0, 0.0))
        return

    if _zip_entity is not None and _zip_entity.isAlive():
        _zip_target = _zip_entity.position().add(0, float(_zip_entity.getBbHeight()) / 2.0, 0)
        _zip_anchor_l = _zip_target
        _zip_anchor_r = _zip_target

    px = float(player.getX())
    py = float(player.getY())
    pz = float(player.getZ())
    tx = float(_zip_target.x)
    ty = float(_zip_target.y)
    tz = float(_zip_target.z)

    dx = tx - px
    dy = ty - py
    dz = tz - pz
    dist = (dx * dx + dy * dy + dz * dz) ** 0.5
    if dist < 0.1:
        _zip_active   = False
        _zip_target   = None
        _zip_entity   = None
        _zip_anchor_l = None
        _zip_anchor_r = None
        _zip_cooldown = ZIP_COOLDOWN
        player.setDeltaMovement(Vec3(0.0, 0.0, 0.0))
        return

    if _zip_converging or _zip_entity is not None:
        nx = dx / dist
        ny = dy / dist
        nz = dz / dist
    else:
        yaw_rad = math.radians(float(player.getYRot(1.0)))
        nx = -math.sin(yaw_rad)
        ny = 0.0
        nz = math.cos(yaw_rad)

    pull_speed = min(speed, dist)
    player.setDeltaMovement(Vec3(nx * pull_speed, ny * pull_speed, nz * pull_speed))
    player.fallDistance = float32(0.0)


def zip_tick(client, player):
    global _zip_prev_key, _zip_cooldown, _zip_active, _zip_holding, _zip_ticks

    zip_down = InputConstants.isKeyDown(Minecraft.getInstance().getWindow(), GLFW_KEY_Z)
    zip_just_pressed = zip_down and not _zip_prev_key
    _zip_prev_key = zip_down

    if _zip_cooldown > 0:
        _zip_cooldown -= 1

    if _zip_active:
        if _zip_holding:
            vel = player.getDeltaMovement()
            player.setDeltaMovement(Vec3(float(vel.x) * 0.25, float(vel.y), float(vel.z) * 0.25))
            if not zip_down:
                if not _zip_converging and _zip_entity is None:
                    yaw_rad = math.radians(float(player.getYRot(1.0)))
                    nx = -math.sin(yaw_rad)
                    nz = math.cos(yaw_rad)
                    player.setDeltaMovement(Vec3(nx * ZIP_BLOCK_SPEED * 4.0, 0.3, nz * ZIP_BLOCK_SPEED * 4.0))
                    player.fallDistance = float32(0.0)
                    _zip_active   = False
                    _zip_target   = None
                    _zip_anchor_l = None
                    _zip_anchor_r = None
                    _zip_cooldown = ZIP_COOLDOWN
                else:
                    _zip_holding = False
                    _zip_ticks = 0
        else:
            _tick_zip(player)
    elif zip_just_pressed and _zip_cooldown == 0 and not _attached and not _tether_active:
        _try_zip(client)


def zip_reset_keys():
    global _zip_prev_key
    _zip_prev_key = False


def zip_render(player, sub, cam):
    if not _zip_active or _zip_anchor_l is None or _zip_anchor_r is None:
        return
    lhx, lhy, lhz = _get_hand_pos(player, sub, 'left')
    rhx, rhy, rhz = _get_hand_pos(player, sub, 'right')
    _draw_strand(
        float(lhx - cam.x), float(lhy - cam.y), float(lhz - cam.z),
        float(_zip_anchor_l.x - cam.x), float(_zip_anchor_l.y - cam.y), float(_zip_anchor_l.z - cam.z),
        1.0, 255)
    _draw_strand(
        float(rhx - cam.x), float(rhy - cam.y), float(rhz - cam.z),
        float(_zip_anchor_r.x - cam.x), float(_zip_anchor_r.y - cam.y), float(_zip_anchor_r.z - cam.z),
        1.0, 255)
