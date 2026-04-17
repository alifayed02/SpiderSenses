"""FOV warp applied while the effect is active."""

from elide.minecraft import mixin

MAX_FOV_GAIN = 0.12


@mixin.modify_return_value(
    "net.minecraft.client.Camera",
    method="calculateFov",
    at="RETURN",
)
def warp_fov(this, original):
    env = fov_envelope(0.0)
    if env <= 0.001:
        return original
    return jf(original * (1.0 + MAX_FOV_GAIN * env))
