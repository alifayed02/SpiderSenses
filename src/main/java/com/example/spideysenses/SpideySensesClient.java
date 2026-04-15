package com.example.spideysenses;

import com.example.spideysenses.mixin.GameRendererAccessor;
import com.example.spideysenses.mixin.PostChainAccessor;
import com.example.spideysenses.mixin.PostPassAccessor;
import com.mojang.blaze3d.buffers.GpuBuffer;
import com.mojang.blaze3d.resource.GraphicsResourceAllocator;
import com.mojang.blaze3d.systems.RenderSystem;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.minecraft.client.Minecraft;
import net.minecraft.client.renderer.GameRenderer;
import net.minecraft.client.renderer.LevelTargetBundle;
import net.minecraft.client.renderer.PostChain;
import net.minecraft.client.renderer.PostPass;
import net.minecraft.client.renderer.state.level.CameraRenderState;
import net.minecraft.resources.Identifier;
import net.minecraft.world.phys.Vec3;
import org.joml.Matrix4f;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.Map;

public class SpideySensesClient implements ClientModInitializer {
    public static final String MOD_ID = "spidey-senses";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    public static final double DETECTION_RADIUS = 16.0;
    public static final float TRIGGER_THRESHOLD = 0.40f;
    public static final float REARM_THRESHOLD = 0.20f;
    public static final int EFFECT_DURATION_TICKS = 100;
    public static final float HOLD_FRACTION = 0.20f;
    public static final float MAX_CHROMATIC_DISTORT = 3.2f;
    public static final float SENSE_EDGE_SOFTNESS = 3.0f;
    public static final float MAX_SHARPEN_AMOUNT = 0.30f;
    public static final float MAX_ZOOM_BLUR = 0.0f;

    public static final ThreatTracker THREAT = new ThreatTracker(DETECTION_RADIUS);

    private static final Identifier CHROMATIC_EFFECT =
        Identifier.fromNamespaceAndPath(MOD_ID, "chromatic");
    private static final Identifier SENSE_WORLD_EFFECT =
        Identifier.fromNamespaceAndPath(MOD_ID, "sense_world");

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
            pushChromaticUniforms(client);
        });
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

    private static void pushChromaticUniforms(Minecraft client) {
        if (!effectActive()) return;
        float distort = MAX_CHROMATIC_DISTORT * envelope(0.0f);
        PostChain chain = client.getShaderManager()
            .getPostChain(CHROMATIC_EFFECT, LevelTargetBundle.MAIN_TARGETS);
        if (chain == null) return;
        for (PostPass pass : ((PostChainAccessor) chain).spideysenses$passes()) {
            Map<String, GpuBuffer> uniforms =
                ((PostPassAccessor) pass).spideysenses$customUniforms();
            if (uniforms.containsKey("AberrationConfig")) {
                writeFloats(uniforms, "AberrationConfig", new float[]{distort});
            }
        }
    }

    public static void runWorldSenseEffect(GraphicsResourceAllocator allocator,
                                            CameraRenderState camera) {
        if (!effectActive()) return;
        if (camera == null || camera.projectionMatrix == null
            || camera.viewRotationMatrix == null || camera.pos == null) return;

        Minecraft client = Minecraft.getInstance();
        PostChain chain = client.getShaderManager()
            .getPostChain(SENSE_WORLD_EFFECT, LevelTargetBundle.MAIN_TARGETS);
        if (chain == null) return;

        pushSenseWorldUniforms(chain, camera);
        chain.process(client.getMainRenderTarget(), allocator);
    }

    private static void pushSenseWorldUniforms(PostChain chain, CameraRenderState camera) {
        float env = envelope(0.0f);
        float maxRadius = camera.depthFar > 0.0f ? camera.depthFar : 512.0f;
        float radius = maxRadius * env;
        float strength = env;

        Vec3 pos = camera.pos;
        Matrix4f view = new Matrix4f(camera.viewRotationMatrix)
            .translate((float) -pos.x, (float) -pos.y, (float) -pos.z);
        Matrix4f invViewProj = new Matrix4f(camera.projectionMatrix).mul(view).invert();
        float[] m = new float[16];
        invViewProj.get(m);

        float[] uniforms = new float[] {
            radius, SENSE_EDGE_SOFTNESS, strength, 0.0f,
            (float) pos.x, (float) pos.y, (float) pos.z, 0.0f,
            m[0], m[1], m[2], m[3],
            m[4], m[5], m[6], m[7],
            m[8], m[9], m[10], m[11],
            m[12], m[13], m[14], m[15]
        };

        float sharpen = MAX_SHARPEN_AMOUNT * env;
        float zoomBlur = MAX_ZOOM_BLUR * fovEnvelope(0.0f);

        for (PostPass pass : ((PostChainAccessor) chain).spideysenses$passes()) {
            Map<String, GpuBuffer> u =
                ((PostPassAccessor) pass).spideysenses$customUniforms();
            if (u.containsKey("SenseConfig")) {
                writeFloats(u, "SenseConfig", uniforms);
            }
            if (u.containsKey("SharpenConfig")) {
                writeFloats(u, "SharpenConfig", new float[]{sharpen});
            }
            if (u.containsKey("ZoomBlurConfig")) {
                writeFloats(u, "ZoomBlurConfig",
                    new float[]{zoomBlur, 0.0f, 0.0f, 0.0f});
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
