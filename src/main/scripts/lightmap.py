"""Lifts the lightmap's night-vision intensity while the effect is active
so dark scenes brighten before the tint pass."""

import java

from elide import mixin

_Vector3f = java.type("org.joml.Vector3f")
_NIGHT_VISION_WHITE = _Vector3f(1.0, 1.0, 1.0)


@mixin.inject(
    "net.minecraft.client.renderer.LightmapRenderStateExtractor",
    method="extract",
    at="TAIL",
)
def lift_night_vision(this, state, partial_tick, ci):
    env = envelope(partial_tick)
    if env <= 0.001:
        return
    if env > state.nightVisionEffectIntensity:
        state.nightVisionEffectIntensity = float32(env)
        state.nightVisionColor = _NIGHT_VISION_WHITE
    state.needsUpdate = True
