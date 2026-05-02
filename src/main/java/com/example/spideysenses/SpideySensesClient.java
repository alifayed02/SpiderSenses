package com.example.spideysenses;

import com.mojang.blaze3d.buffers.GpuBuffer;
import com.mojang.blaze3d.systems.RenderSystem;
import dev.elide.lang.minecraft.PolyglotDispatch;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.ByteBuffer;

/**
 * Fabric entrypoint. All mod logic lives under {@code src/main/scripts/}.
 */
public class SpideySensesClient implements ClientModInitializer {
    public static final String MOD_ID = "spidey-senses";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    private static final String STATE_SCRIPT = "src/main/scripts/state.py";
    private static final String WEB_SCRIPT   = "src/main/scripts/web.py";

    @Override
    public void onInitializeClient() {
        LOGGER.info("{} initialized", MOD_ID);
        PolyglotDispatch.call("python", STATE_SCRIPT, "prime");
        PolyglotDispatch.call("python", WEB_SCRIPT, "prime");
        ClientTickEvents.END_CLIENT_TICK.register(
            client -> PolyglotDispatch.call("python", STATE_SCRIPT, "on_client_tick", client)
        );
    }

    /**
     * Allocates a new GpuBuffer with COPY_DST added to the usage flags and
     * seeds it with {@code initial}. Bridged from Python because Elide ships
     * GraalPy 25.0.2, whose legacy inheritance semantics don't support
     * implementing functional interfaces like {@link java.util.function.Supplier}.
     * Revisit when Elide bundles GraalPy 25.2+ (which defaults to {@code new_style=True}).
     */
    public static GpuBuffer upgradeBuffer(GpuBuffer old, String name, ByteBuffer initial) {
        int usage = old.usage() | GpuBuffer.USAGE_COPY_DST;
        GpuBuffer replacement = RenderSystem.getDevice().createBuffer(() -> name, usage, initial);
        old.close();
        return replacement;
    }
}
