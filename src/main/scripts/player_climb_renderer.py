"""Player climbing orientation – swim X-rotation + WASD roll + crawl-style limb animation.

Limb animation is ported from the crawl mod (ru.fewizz.crawl) –
common/src/main/java/ru/fewizz/crawl/client/mixin/HumanoidModelMixin.java
"""

import math

import java
from elide import float32, mixin

Axis = java.type("com.mojang.math.Axis")
Minecraft = java.type("net.minecraft.client.Minecraft")
AvatarRenderState = java.type("net.minecraft.client.renderer.entity.state.AvatarRenderState")
Mth = java.type("net.minecraft.util.Mth")
HumanoidArm = java.type("net.minecraft.world.entity.HumanoidArm")
InteractionHand = java.type("net.minecraft.world.InteractionHand")

PI = math.pi

ROLL_LERP = 0.2

_climb_roll_current = 0.0


def _is_climbing():
    try:
        return _wall_active and _wall_mode == 'climb'
    except NameError:
        return False


def _wall_facing_yaw():
    """Yaw (deg) needed for the player to face the wall, given the wall normal."""
    try:
        if _wall_normal is None:
            return 0.0
        nx, nz = _wall_normal
    except NameError:
        return 0.0
    return math.degrees(math.atan2(nx, -nz))


def _magic_f0(rad):
    rad = rad % (PI * 2.0)
    if rad <= PI / 2.0:
        return math.cos(rad * 2.0)
    return -math.cos((rad - PI / 2.0) * (2.0 / 3.0))


def _magic_f1(rad):
    r = math.sin(rad) + 1.0
    return r * r


def _lerp(t, a, b):
    return a + (b - a) * t


def _rot_lerp_rad(t, a, b):
    return float(Mth.rotLerpRad(float32(t), float32(a), float32(b)))


def _l_pos(lp, mp, x, y, z):
    mp.setPos(
        float32(_lerp(lp, float(mp.x), x)),
        float32(_lerp(lp, float(mp.y), y)),
        float32(_lerp(lp, float(mp.z), z)),
    )


def _l_rot(lp, mp, roll, yaw, pitch):
    mp.zRot = float32(_rot_lerp_rad(lp, float(mp.zRot), roll))
    mp.yRot = float32(_rot_lerp_rad(lp, float(mp.yRot), yaw))
    mp.xRot = float32(_rot_lerp_rad(lp, float(mp.xRot), pitch))


@mixin.inject(
    "net.minecraft.client.renderer.entity.LivingEntityRenderer",
    method="submit",
    at="HEAD",
)
def setup_climb_swim(this, state, poseStack, collector, camera, ci):
    if not _is_climbing():
        return
    if not isinstance(state, AvatarRenderState):
        return
    state.swimAmount = float32(1.0)
    wall_yaw = _wall_facing_yaw()
    state.bodyRot = float32(wall_yaw)
    state.yRot = float32(0.0)
    state.xRot = float32(0.0)
    try:
        state.walkAnimationPos = float32(_wall_anim_pos)
        state.walkAnimationSpeed = float32(_wall_anim_speed)
    except NameError:
        pass


@mixin.inject(
    "net.minecraft.client.renderer.entity.player.AvatarRenderer",
    method="setupRotations",
    at="TAIL",
)
def climb_roll(this, state, poseStack, bodyRot, entityScale, ci):
    global _climb_roll_current
    if not _is_climbing():
        _climb_roll_current = 0.0
        return
    mc = Minecraft.getInstance()
    if mc.player is None:
        return

    poseStack.mulPose(Axis.XP.rotationDegrees(float32(90.0)))

    kp = mc.player.input.keyPresses
    up_comp = (1.0 if kp.forward() else 0.0) - (1.0 if kp.backward() else 0.0)
    left_comp = (1.0 if kp.left() else 0.0) - (1.0 if kp.right() else 0.0)
    if up_comp == 0.0 and left_comp == 0.0:
        target = 0.0
    else:
        target = math.degrees(math.atan2(left_comp, up_comp))

    _climb_roll_current = float(Mth.rotLerp(
        float32(ROLL_LERP), float32(_climb_roll_current), float32(target)
    ))

    if abs(_climb_roll_current) > 0.05:
        half_h = float(state.boundingBoxHeight) / 2.0
        poseStack.translate(float32(0.0), float32(half_h), float32(0.0))
        poseStack.mulPose(Axis.ZP.rotationDegrees(float32(_climb_roll_current)))
        poseStack.translate(float32(0.0), float32(-half_h), float32(0.0))


@mixin.inject(
    "net.minecraft.client.model.HumanoidModel",
    method="setupAnim",
    at="TAIL",
)
def climb_crawl_anim(this, state, ci):
    if not _is_climbing():
        return
    if not isinstance(state, AvatarRenderState):
        return

    head = this.head
    body = this.body
    right_arm = this.rightArm
    left_arm = this.leftArm
    right_leg = this.rightLeg
    left_leg = this.leftLeg

    walk_dist = float(state.walkAnimationPos)
    sa = float(state.swimAmount)
    body_y_rot_freq = 6.0
    body_x_rot = 0.0
    body_y_rot = math.sin(walk_dist) / 5.0
    z_offset = 0.0
    y_offset = 0.0

    _l_pos(
        sa, left_leg,
        float(left_leg.x) + math.sin(walk_dist) / body_y_rot_freq * float(left_leg.y),
        float(left_leg.y) + _magic_f0(walk_dist - 3.0 / 4.0 * PI) * 2.0 - 1.0 + y_offset,
        _magic_f0(walk_dist - PI / 2.0) + z_offset,
    )
    _l_rot(sa, left_leg, -_magic_f1(walk_dist + PI) / 6.0, body_y_rot, 0.0)

    _l_pos(
        sa, right_leg,
        float(right_leg.x) + math.sin(walk_dist) / body_y_rot_freq * float(right_leg.y),
        float(right_leg.y) + _magic_f0(walk_dist + PI / 4.0) * 2.0 - 1.0 + y_offset,
        _magic_f0(walk_dist + PI / 2.0) + z_offset,
    )
    _l_rot(sa, right_leg, _magic_f1(walk_dist) / 6.0, body_y_rot, 0.0)

    body_height = 12.0
    body_x_rot_orig = float(body.xRot)
    _l_pos(
        sa, body,
        float(body.x),
        (1.0 - math.cos(_rot_lerp_rad(sa, body_x_rot_orig, body_x_rot))) * body_height + y_offset,
        -math.sin(_rot_lerp_rad(sa, body_x_rot_orig, body_x_rot)) * body_height + z_offset,
    )
    _l_rot(sa, body, -math.sin(walk_dist) / body_y_rot_freq, body_y_rot, body_x_rot)

    _l_pos(
        sa, head,
        float(head.x),
        float(head.y) + y_offset,
        float(head.z) + math.cos(walk_dist * 2.0) / 2.0 + z_offset,
    )
    _l_rot(sa, head, -float(head.yRot), 0.0, float(head.xRot) - PI / 2.0)

    using_off = state.isUsingItem and (
        (state.useItemHand == InteractionHand.OFF_HAND) == (state.mainArm == HumanoidArm.LEFT)
    )
    attacking_left = state.attackTime > 0 and state.attackArm == HumanoidArm.LEFT
    if using_off or attacking_left:
        _l_rot(sa, left_arm, -float(left_arm.yRot), 0.0, float(left_arm.xRot) - PI / 2.0)
    else:
        _l_rot(
            sa, left_arm,
            -PI / 2.0 + _magic_f0(walk_dist + PI / 2.0),
            float(body.yRot) - PI / 2.0,
            -0.5,
        )

    using_main = state.isUsingItem and (
        (state.useItemHand == InteractionHand.MAIN_HAND) == (state.mainArm == HumanoidArm.RIGHT)
    )
    attacking_right = state.attackTime > 0 and state.attackArm == HumanoidArm.RIGHT
    if using_main or attacking_right:
        _l_rot(sa, right_arm, -float(right_arm.yRot), 0.0, float(right_arm.xRot) - PI / 2.0)
    else:
        _l_rot(
            sa, right_arm,
            PI / 2.0 + -_magic_f0(walk_dist - PI / 2.0),
            float(body.yRot) + PI / 2.0,
            -0.5,
        )
