"""Mixin accessors and invokers.

Bodies are placeholders. Elide's build-time resolver introspects each
target to build the descriptor, and Sponge Mixin grafts the field
access or method invocation onto the target class bytecode.
"""

from elide.minecraft import mixin


@mixin.invoker("net.minecraft.client.renderer.GameRenderer", method="setPostEffect")
def spideysenses_setPostEffect(this, identifier):
    pass


@mixin.accessor("net.minecraft.client.renderer.PostChain", method="passes")
def spideysenses_passes(this):
    pass


@mixin.accessor("net.minecraft.client.renderer.PostPass", method="customUniforms")
def spideysenses_customUniforms(this):
    pass
