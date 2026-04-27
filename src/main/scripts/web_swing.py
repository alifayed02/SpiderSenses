"""Web swinging – input detection, raycasting, pendulum physics, and line rendering."""

import java

from elide import float32

Minecraft          = java.type("net.minecraft.client.Minecraft")
ClipContext        = java.type("net.minecraft.world.level.ClipContext")
ClipBlock          = java.type("net.minecraft.world.level.ClipContext$Block")
ClipFluid          = java.type("net.minecraft.world.level.ClipContext$Fluid")
HitType            = java.type("net.minecraft.world.phys.HitResult$Type")
DustParticleOptions = java.type("net.minecraft.core.particles.DustParticleOptions")

WEB_MAX_RANGE = 64.0
WEB_ROPE_MIN  = 3.0

_WHITE_DUST  = DustParticleOptions(0xFFFFFF, float32(0.35))
_attached    = False
_anchor      = None
_rope_length = 0.0
_prev_use    = False
_spawn_tick  = 0


def prime():
    return None


def _try_shoot(client):
    global _attached, _anchor, _rope_length
    player = client.player
    level  = client.level
    if player is None or level is None:
        return
    if not player.getMainHandItem().isEmpty():
        return

    eye  = player.getEyePosition()
    look = player.getViewVector(1.0)
    end  = eye.add(look.scale(WEB_MAX_RANGE))
    hit  = level.clip(
        ClipContext(eye, end, ClipBlock.COLLIDER, ClipFluid.NONE, player)
    )
    if hit.getType() != HitType.BLOCK:
        return

    _anchor      = hit.getLocation()
    _rope_length = max(WEB_ROPE_MIN, player.position().distanceTo(_anchor))
    _attached    = True


def _detach():
    global _attached, _anchor, _rope_length
    _attached    = False
    _anchor      = None
    _rope_length = 0.0


def _apply_pendulum(player):
    global _rope_length
    px = player.getX() - _anchor.x
    py = player.getY() - _anchor.y
    pz = player.getZ() - _anchor.z
    dist = (px * px + py * py + pz * pz) ** 0.5
    if dist < 1.0e-4:
        return

    rx, ry, rz = px / dist, py / dist, pz / dist

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


def _spawn_web_particles(client):
    global _spawn_tick
    _spawn_tick += 1
    if _spawn_tick % 2 != 0:
        return
    player = client.player
    level  = client.level
    if player is None or level is None:
        return

    hand = player.getEyePosition()
    dx = _anchor.x - hand.x
    dy = _anchor.y - hand.y
    dz = _anchor.z - hand.z
    dist = (dx * dx + dy * dy + dz * dz) ** 0.5
    steps = min(30, max(1, int(dist)))
    for i in range(steps + 1):
        t = i / steps
        level.addParticle(
            _WHITE_DUST,
            hand.x + dx * t, hand.y + dy * t, hand.z + dz * t,
            0.0, 0.0, 0.0,
        )


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
        _spawn_web_particles(client)
        if player.onGround():
            dist = player.position().distanceTo(_anchor)
            if dist > _rope_length:
                _rope_length = dist
        else:
            _apply_pendulum(player)
    elif just_pressed:
        _try_shoot(client)
