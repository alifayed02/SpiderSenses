"""
Mixin accessors/invokers ported from the Java mixin/ package.

Elide's build-time resolver introspects each target class to build
the correct descriptor (getter vs setter for @Accessor, full method
signature for @Invoker), so the function bodies here never run —
Sponge Mixin grafts the real field access / method call onto the
target class bytecode. Bodies are kept as `pass` placeholders.

Python identifiers can't contain '$', so the grafted method names
use underscores instead of the Sponge convention's '$'.
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
