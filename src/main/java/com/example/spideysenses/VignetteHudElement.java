package com.example.spideysenses;

import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElement;
import net.minecraft.client.DeltaTracker;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.renderer.RenderPipelines;
import net.minecraft.resources.Identifier;

public class VignetteHudElement implements HudElement {
    private static final int FRAME_COUNT = 16;
    private static final float TICKS_PER_FRAME = 1.5f;
    private static final Identifier[] FRAMES = new Identifier[FRAME_COUNT];

    static {
        for (int i = 0; i < FRAME_COUNT; i++) {
            FRAMES[i] = Identifier.fromNamespaceAndPath(
                SpideySensesClient.MOD_ID, "textures/sense/" + (i + 1) + ".png");
        }
    }

    @Override
    public void extractRenderState(GuiGraphicsExtractor graphics, DeltaTracker delta) {
        if (!SpideySensesClient.effectActive()) return;
        float subTick = delta.getGameTimeDeltaPartialTick(true);
        float ticks = SpideySensesClient.effectTicks(subTick);
        float env = SpideySensesClient.envelope(subTick);
        if (env <= 0.01f) return;

        int frame = Math.min((int) (ticks / TICKS_PER_FRAME), FRAME_COUNT - 1);

        int width = graphics.guiWidth();
        int height = graphics.guiHeight();
        int alpha = (int) (env * 255.0f) & 0xFF;
        int color = (alpha << 24) | 0xFFFFFF;

        graphics.blit(
            RenderPipelines.GUI_TEXTURED,
            FRAMES[frame],
            0, 0,
            0.0f, 0.0f,
            width, height,
            width, height,
            color
        );
    }
}
