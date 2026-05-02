"""Web abilities orchestrator – shared infra, module loading, tick/render dispatch."""

import java
import math

from elide import float32

Logger      = java.type("com.example.spideysenses.SpideySensesClient").LOGGER
Minecraft   = java.type("net.minecraft.client.Minecraft")
ClipContext = java.type("net.minecraft.world.level.ClipContext")
ClipBlock   = java.type("net.minecraft.world.level.ClipContext$Block")
ClipFluid   = java.type("net.minecraft.world.level.ClipContext$Fluid")
HitType     = java.type("net.minecraft.world.phys.HitResult$Type")
RenderTypes  = java.type("net.minecraft.client.renderer.rendertype.RenderTypes")
Tesselator   = java.type("com.mojang.blaze3d.vertex.Tesselator")
RenderSystem = java.type("com.mojang.blaze3d.systems.RenderSystem")
MoverType    = java.type("net.minecraft.world.entity.MoverType")
Vec3             = java.type("net.minecraft.world.phys.Vec3")
InputConstants   = java.type("com.mojang.blaze3d.platform.InputConstants")

WEB_SEGMENTS   = 24
WEB_HALF_WIDTH = 0.025
FULL_BRIGHT    = 15728880


def _get_hand_pos(player, sub, side='right'):
    mc  = Minecraft.getInstance()
    pos = player.getPosition(sub)
    if mc.options.getCameraType().isFirstPerson():
        pitch = math.radians(float(player.getXRot(sub)))
        yaw   = math.radians(float(player.getYRot(sub)))
        ox = -0.3 if side == 'right' else 0.3
        oy, oz = -0.15, 0.4
        cos_p = math.cos(pitch)
        sin_p = math.sin(pitch)
        ry   = oy * cos_p - oz * sin_p
        rz_r = oy * sin_p + oz * cos_p
        cos_y = math.cos(yaw)
        sin_y = math.sin(yaw)
        hx = ox * cos_y - rz_r * sin_y
        hz = ox * sin_y + rz_r * cos_y
        hy = ry
        return (float(pos.x) + hx, float(pos.y) + float(player.getEyeHeight()) + hy, float(pos.z) + hz)
    else:
        by = math.radians(float(player.yBodyRotO) + (float(player.yBodyRot) - float(player.yBodyRotO)) * sub)
        cos_by = math.cos(by)
        sin_by = math.sin(by)
        renderer = mc.getEntityRenderDispatcher().getRenderer(player)
        model    = renderer.getModel()
        if side == 'right':
            arm_pitch = float(model.rightArm.xRot)
        else:
            arm_pitch = float(model.leftArm.xRot)
        arm_len   = 10.0 / 16.0
        tip_down  = -arm_len * math.cos(arm_pitch)
        tip_fwd   = arm_len * math.sin(arm_pitch)
        sign = -1.0 if side == 'right' else 1.0
        return (
            float(pos.x) + sign * cos_by * 5.0 / 16.0 - sin_by * tip_fwd,
            float(pos.y) + 22.0 / 16.0 + tip_down,
            float(pos.z) + sign * sin_by * 5.0 / 16.0 + cos_by * tip_fwd,
        )


def _draw_strand(sx, sy, sz, ex, ey, ez, t_interp, alpha, cr=255, cg=255, cb=255):
    rdx = ex - sx
    rdy = ey - sy
    rdz = ez - sz
    rope_len = (rdx * rdx + rdy * rdy + rdz * rdz) ** 0.5
    if rope_len < 0.1:
        return

    rt = 1.0 - t_interp
    segments = 1 if rt < 0.001 else WEB_SEGMENTS

    if sy > ey:
        mid_x, mid_y, mid_z = sx, sy + (ey - sy) * rt * 2.0, sz
    else:
        mid_x, mid_y, mid_z = ex, ey + (sy - ey) * rt * 2.0, ez

    hw = WEB_HALF_WIDTH

    leash = RenderTypes.leash()
    builder = Tesselator.getInstance().begin(leash.mode(), leash.format())

    for i in range(segments + 1):
        t = i / segments
        u = 1.0 - t
        px = u * u * sx + 2.0 * u * t * mid_x + t * t * ex
        py = u * u * sy + 2.0 * u * t * mid_y + t * t * ey
        pz = u * u * sz + 2.0 * u * t * mid_z + t * t * ez

        bx = rdy * pz - rdz * py
        by = rdz * px - rdx * pz
        bz = rdx * py - rdy * px
        bl = (bx * bx + by * by + bz * bz) ** 0.5
        if bl < 1.0e-6:
            bx, by, bz = 0.0, hw, 0.0
        else:
            bx = bx / bl * hw
            by = by / bl * hw
            bz = bz / bl * hw

        builder.addVertex(float32(px - bx), float32(py - by), float32(pz - bz)).setColor(cr, cg, cb, alpha).setLight(FULL_BRIGHT)
        builder.addVertex(float32(px + bx), float32(py + by), float32(pz + bz)).setColor(cr, cg, cb, alpha).setLight(FULL_BRIGHT)

    mesh = builder.buildOrThrow()
    leash.draw(mesh)


exec(open("src/main/scripts/web_swing.py").read())
exec(open("src/main/scripts/web_zip.py").read())
exec(open("src/main/scripts/web_tether.py").read())
exec(open("src/main/scripts/web_wall_run.py").read())
exec(open("src/main/scripts/web_charge_jump.py").read())


def prime():
    return None


def web_tick(client):
    player = client.player
    if player is None or client.isPaused():
        swing_reset_keys()
        zip_reset_keys()
        tether_reset_keys()
        wall_reset_keys()
        charge_jump_reset_keys()
        return

    swing_tick(client, player)
    tether_tick(client, player)
    zip_tick(client, player)
    wall_tick(client, player)
    charge_jump_tick(client, player)


def render_web_line(level_renderer, camera, delta):
    if not _attached and not _zip_active and not _tether_active and _detached is None:
        return
    player = Minecraft.getInstance().player
    if player is None:
        return

    sub = float(delta.getGameTimeDeltaPartialTick(True))
    cam = camera.pos

    mv = RenderSystem.getModelViewStack()
    mv.pushMatrix()
    mv.set(camera.viewRotationMatrix)

    swing_render(player, sub, cam)
    zip_render(player, sub, cam)
    tether_render(player, sub, cam)

    mv.popMatrix()
