package com.example.spideysenses.mixin;

import com.example.spideysenses.SpideySensesClient;
import com.llamalad7.mixinextras.injector.ModifyReturnValue;
import net.minecraft.client.Camera;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;

@Mixin(Camera.class)
public class CameraMixin {
    private static final float MAX_FOV_GAIN = 0.22f;

    @ModifyReturnValue(method = "calculateFov(F)F", at = @At("RETURN"))
    private float spideysenses$warpFov(float original, float partialTick) {
        float env = SpideySensesClient.fovEnvelope(partialTick);
        if (env <= 0.001f) return original;
        return original * (1.0f + MAX_FOV_GAIN * env);
    }
}
