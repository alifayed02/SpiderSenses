"""Runs the world-space sense post-effect at LevelRenderer.renderLevel TAIL,
where minecraft:main's depth buffer is still valid."""

from elide import mixin


@mixin.inject(
    "net.minecraft.client.renderer.LevelRenderer",
    method="renderLevel",
    at="TAIL",
)
def run_sense_effect(
    this,
    allocator,
    delta,
    render_block_outline,
    camera,
    frustum_matrix,
    fog_buffer,
    fog_color,
    is_shadow_active,
    chunks,
    ci,
):
    run_world_sense_effect(allocator, camera)
