"""Rappel camera roll via GameRenderer.bobHurt PoseStack.

The bobHurt PoseStack is multiplied into the projection matrix, so a
Z-rotation here affects the entire rendered scene (sky, chunks, entities,
hand) without touching the view rotation matrix or frustum culling.
"""

import java
import math

from elide import float32, mixin

Axis = java.type("com.mojang.math.Axis")
Minecraft = java.type("net.minecraft.client.Minecraft")


@mixin.inject(
    "net.minecraft.client.renderer.GameRenderer",
    method="bobHurt",
    at="HEAD",
)
def apply_rappel_roll(this, camera_state, pose_stack, ci):
    prev = _rappel_prev_timer
    cur = _rappel_timer
    if prev == 0.0 and cur == 0.0:
        return
    sub = float(Minecraft.getInstance().getDeltaTracker().getGameTimeDeltaPartialTick(True))
    t = prev + (cur - prev) * sub
    pose_stack.mulPose(Axis.ZP.rotationDegrees(float32(t * 180.0)))
