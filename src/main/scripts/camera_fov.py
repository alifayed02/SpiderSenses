"""
Zoom-in FOV warp while the spidey-sense effect is active.

@ModifyReturnValue on Camera.calculateFov. Bridge signature (F)F doesn't
forward partial_tick, so we use fov_envelope(0) — tick-rate granularity.
"""

from elide.minecraft import mixin

MAX_FOV_GAIN = 0.12


@mixin.modify_return_value(
    "net.minecraft.client.Camera",
    method="calculateFov",
    at="RETURN",
)
def warp_fov(this, original):
    env = fov_envelope(0.0)  # defined in state.py (shared __main__)
    if env <= 0.001:
        return original
    return jf(original * (1.0 + MAX_FOV_GAIN * env))  # pre-narrow to pass Java float check
