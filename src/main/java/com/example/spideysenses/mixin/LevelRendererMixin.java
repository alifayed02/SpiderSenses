package com.example.spideysenses.mixin;

import com.example.spideysenses.SpideySensesClient;
import com.mojang.blaze3d.buffers.GpuBufferSlice;
import com.mojang.blaze3d.resource.GraphicsResourceAllocator;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.renderer.LevelRenderer;
import net.minecraft.client.renderer.chunk.ChunkSectionsToRender;
import net.minecraft.client.renderer.state.level.CameraRenderState;
import org.joml.Matrix4fc;
import org.joml.Vector4f;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

@Mixin(LevelRenderer.class)
public class LevelRendererMixin {
    @Inject(method = "renderLevel", at = @At("TAIL"))
    private void spideysenses$runSenseEffect(
        GraphicsResourceAllocator allocator,
        DeltaTracker delta,
        boolean renderBlockOutline,
        CameraRenderState camera,
        Matrix4fc frustumMatrix,
        GpuBufferSlice fogBuffer,
        Vector4f fogColor,
        boolean isShadowActive,
        ChunkSectionsToRender chunks,
        CallbackInfo ci
    ) {
        SpideySensesClient.runWorldSenseEffect(allocator, camera);
    }
}
