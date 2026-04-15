package com.example.spideysenses.mixin;

import com.example.spideysenses.SpideySensesClient;
import net.minecraft.client.renderer.LightmapRenderStateExtractor;
import net.minecraft.client.renderer.state.LightmapRenderState;
import org.joml.Vector3f;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(LightmapRenderStateExtractor.class)
public class LightmapRenderStateExtractorMixin {
    private static final Vector3f NIGHT_VISION_WHITE = new Vector3f(1.0f, 1.0f, 1.0f);

    @Inject(method = "extract", at = @At("TAIL"))
    private void spideysenses$liftNightVision(LightmapRenderState state,
                                               float partialTick,
                                               CallbackInfo ci) {
        float env = SpideySensesClient.envelope(partialTick);
        if (env <= 0.001f) return;
        if (env > state.nightVisionEffectIntensity) {
            state.nightVisionEffectIntensity = env;
            state.nightVisionColor = NIGHT_VISION_WHITE;
        }
        state.needsUpdate = true;
    }
}
