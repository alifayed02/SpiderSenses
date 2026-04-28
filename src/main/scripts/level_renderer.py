"""LevelRenderer.renderLevel TAIL hook for web line rendering + sense post-effect."""

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
    render_web_line(this, camera, delta)
    run_world_sense_effect(allocator, camera)
