"""Web charge jump – hold X to charge in place, release to launch in momentum direction."""

GLFW_KEY_X = 88

CHARGE_MAX_TICKS = 30
CHARGE_MIN_TICKS = 3
CHARGE_COOLDOWN = 20

JUMP_HORIZONTAL_MAX = 2.0
JUMP_VERTICAL_MAX = 1.5
JUMP_VERTICAL_PURE = 2.2

MOMENTUM_MIN = 0.05

_charge_active = False
_charge_ticks = 0
_charge_dir = None
_charge_prev_key = False
_charge_cooldown = 0


def _capture_horizontal_momentum(player):
    """Returns (dx, dz) unit vector of horizontal momentum, or None if below threshold."""
    vel = player.getDeltaMovement()
    vx, vz = float(vel.x), float(vel.z)
    mag = (vx * vx + vz * vz) ** 0.5
    if mag < MOMENTUM_MIN:
        return None
    return (vx / mag, vz / mag)


def _other_web_busy():
    try:
        return _attached or _zip_active or _tether_active or _wall_active
    except NameError:
        return False


def _start_charge(player):
    global _charge_active, _charge_ticks, _charge_dir
    _charge_dir = _capture_horizontal_momentum(player)
    _charge_active = True
    _charge_ticks = 0
    Logger.info("[charge] START dir={}", str(_charge_dir))


def _hold_charge(player):
    global _charge_ticks
    if _charge_ticks < CHARGE_MAX_TICKS:
        _charge_ticks += 1
    player.setDeltaMovement(Vec3(0.0, 0.0, 0.0))
    player.fallDistance = float32(0.0)


def _release_charge(player):
    global _charge_active, _charge_ticks, _charge_cooldown, _charge_dir

    if _charge_ticks < CHARGE_MIN_TICKS:
        _charge_active = False
        _charge_ticks = 0
        _charge_dir = None
        return

    t = _charge_ticks / CHARGE_MAX_TICKS

    if _charge_dir is not None:
        dx, dz = _charge_dir
        h = JUMP_HORIZONTAL_MAX * t
        vy = JUMP_VERTICAL_MAX * t
        player.setDeltaMovement(Vec3(dx * h, vy, dz * h))
    else:
        player.setDeltaMovement(Vec3(0.0, JUMP_VERTICAL_PURE * t, 0.0))

    player.fallDistance = float32(0.0)
    Logger.info("[charge] JUMP ticks={} t={}", str(_charge_ticks), str(round(t, 2)))

    _charge_active = False
    _charge_ticks = 0
    _charge_dir = None
    _charge_cooldown = CHARGE_COOLDOWN


def charge_jump_tick(client, player):
    global _charge_prev_key, _charge_cooldown

    x_down = InputConstants.isKeyDown(Minecraft.getInstance().getWindow(), GLFW_KEY_X)
    x_just_pressed = x_down and not _charge_prev_key
    x_just_released = not x_down and _charge_prev_key
    _charge_prev_key = x_down

    if _charge_cooldown > 0:
        _charge_cooldown -= 1

    if _charge_active:
        if x_just_released:
            _release_charge(player)
        else:
            _hold_charge(player)
    elif x_just_pressed and _charge_cooldown == 0 and not _other_web_busy():
        _start_charge(player)


def charge_jump_reset_keys():
    global _charge_prev_key
    _charge_prev_key = False
