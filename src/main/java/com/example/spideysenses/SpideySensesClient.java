package com.example.spideysenses;

import com.example.spideysenses.mixin.GameRendererAccessor;
import com.example.spideysenses.mixin.PostChainAccessor;
import com.example.spideysenses.mixin.PostPassAccessor;
import com.mojang.blaze3d.buffers.GpuBuffer;
import com.mojang.blaze3d.systems.RenderSystem;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.rendering.v1.hud.HudElementRegistry;
import net.fabricmc.fabric.api.client.rendering.v1.hud.VanillaHudElements;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.GameRenderer;
import net.minecraft.client.renderer.LevelTargetBundle;
import net.minecraft.client.renderer.PostChain;
import net.minecraft.client.renderer.PostPass;
import net.minecraft.resources.Identifier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.List;
import java.util.Map;

public class SpideySensesClient implements ClientModInitializer {
    public static final String MOD_ID = "spidey-senses";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    public static final double DETECTION_RADIUS = 16.0;
    public static final float TRIGGER_THRESHOLD = 0.40f;
    public static final float REARM_THRESHOLD = 0.20f;
    public static final int EFFECT_DURATION_TICKS = 100;
    public static final float HOLD_FRACTION = 0.20f;
    public static final float MAX_CHROMATIC_DISTORT = 4.5f;
    public static final float MAX_SHARPEN_AMOUNT = 0.50f;

    public static final ThreatTracker THREAT = new ThreatTracker(DETECTION_RADIUS);

    private static final Identifier CHROMATIC_EFFECT =
        Identifier.fromNamespaceAndPath(MOD_ID, "chromatic");

    private static volatile int triggerTicks = -1;
    private static boolean armed = true;
    private static boolean effectApplied = false;

    @Override
    public void onInitializeClient() {
        LOGGER.info("{} initialized", MOD_ID);

        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            THREAT.tick(client);
            advanceTrigger();
            updatePostEffect(client);
            pushEffectUniforms(client);
        });

        HudElementRegistry.attachElementAfter(
            VanillaHudElements.MISC_OVERLAYS,
            Identifier.fromNamespaceAndPath(MOD_ID, "vignette"),
            new VignetteHudElement()
        );
    }

    private static void advanceTrigger() {
        float threat = THREAT.level();
        if (threat < REARM_THRESHOLD) armed = true;
        if (armed && threat >= TRIGGER_THRESHOLD && triggerTicks < 0) {
            triggerTicks = 0;
            armed = false;
        }
        if (triggerTicks >= 0) {
            triggerTicks++;
            if (triggerTicks >= EFFECT_DURATION_TICKS) {
                triggerTicks = -1;
            }
        }
    }

    public static boolean effectActive() {
        return triggerTicks >= 0;
    }

    public static float envelope(float subTick) {
        if (triggerTicks < 0) return 0.0f;
        float progress = (triggerTicks + subTick) / (float) EFFECT_DURATION_TICKS;
        if (progress >= 1.0f) return 0.0f;
        float riseEnd = 0.15f;
        float holdEnd = riseEnd + HOLD_FRACTION;
        if (progress < riseEnd) {
            return smoothstep(progress / riseEnd);
        }
        if (progress < holdEnd) {
            return 1.0f;
        }
        return 1.0f - smoothstep((progress - holdEnd) / (1.0f - holdEnd));
    }

    public static float effectTicks(float subTick) {
        return triggerTicks < 0 ? -1.0f : triggerTicks + subTick;
    }

    public static float fovEnvelope(float subTick) {
        if (triggerTicks < 0) return 0.0f;
        float progress = (triggerTicks + subTick) / (float) EFFECT_DURATION_TICKS;
        if (progress >= 1.0f) return 0.0f;
        float peak = 0.25f;
        if (progress < peak) {
            return smoothstep(progress / peak);
        }
        return 1.0f - smoothstep((progress - peak) / (1.0f - peak));
    }

    private static float smoothstep(float t) {
        t = Math.max(0.0f, Math.min(1.0f, t));
        return t * t * (3.0f - 2.0f * t);
    }

    private static void pushEffectUniforms(Minecraft client) {
        if (!effectActive()) return;
        float env = envelope(0.0f);
        float distort = MAX_CHROMATIC_DISTORT * env;
        float sharpen = MAX_SHARPEN_AMOUNT * env;

        PostChain chain = client.getShaderManager()
            .getPostChain(CHROMATIC_EFFECT, LevelTargetBundle.MAIN_TARGETS);
        if (chain == null) return;
        for (PostPass pass : ((PostChainAccessor) chain).spideysenses$passes()) {
            Map<String, GpuBuffer> uniforms =
                ((PostPassAccessor) pass).spideysenses$customUniforms();
            if (uniforms.containsKey("AberrationConfig")) {
                writeFloats(uniforms, "AberrationConfig", new float[]{distort});
            }
            if (uniforms.containsKey("SharpenConfig")) {
                writeFloats(uniforms, "SharpenConfig", new float[]{sharpen});
            }
        }
    }

    private static void writeFloats(Map<String, GpuBuffer> uniforms, String key, float[] values) {
        GpuBuffer buf = uniforms.get(key);
        if (buf == null) return;
        int byteCount = values.length * 4;
        if ((buf.usage() & GpuBuffer.USAGE_COPY_DST) == 0) {
            int size = (int) buf.size();
            ByteBuffer initial = ByteBuffer.allocateDirect(size).order(ByteOrder.LITTLE_ENDIAN);
            for (float v : values) initial.putFloat(v);
            while (initial.hasRemaining()) initial.put((byte) 0);
            initial.rewind();
            GpuBuffer replacement = RenderSystem.getDevice().createBuffer(
                () -> MOD_ID + "-" + key,
                buf.usage() | GpuBuffer.USAGE_COPY_DST,
                initial
            );
            uniforms.put(key, replacement);
            buf.close();
        } else {
            ByteBuffer bb = ByteBuffer.allocateDirect(byteCount).order(ByteOrder.LITTLE_ENDIAN);
            for (float v : values) bb.putFloat(v);
            bb.rewind();
            RenderSystem.getDevice().createCommandEncoder()
                .writeToBuffer(buf.slice(0L, byteCount), bb);
        }
    }

    private static void updatePostEffect(Minecraft client) {
        GameRenderer renderer = client.gameRenderer;
        if (renderer == null) return;
        boolean shouldApply = effectActive();
        if (shouldApply && !effectApplied) {
            ((GameRendererAccessor) renderer).spideysenses$setPostEffect(CHROMATIC_EFFECT);
            effectApplied = true;
        } else if (!shouldApply && effectApplied) {
            if (CHROMATIC_EFFECT.equals(renderer.currentPostEffect())) {
                renderer.clearPostEffect();
            }
            effectApplied = false;
        }
    }
}
