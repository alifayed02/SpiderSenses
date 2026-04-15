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
 * Fabric needs a JVM class it can resolve via {@code Class.forName()}, so this is
 * the thinnest possible shell. All state, threat tracking, envelopes, mixins, and
 * per-tick logic live under {@code src/main/scripts/}.
 *
 * <p>{@link #upgradeBuffer} stays in Java because GraalPy in Elide's embedded
 * configuration can neither coerce a Python lambda to {@code Supplier<String>}
 * nor subclass the interface from Python (host-access proxy disabled).</p>
 */
public class SpideySensesClient implements ClientModInitializer {
    public static final String MOD_ID = "spidey-senses";
    public static final Logger LOGGER = LoggerFactory.getLogger(MOD_ID);

    private static final String STATE_SCRIPT = "src/main/scripts/state.py";

    @Override
    public void onInitializeClient() {
        LOGGER.info("{} initialized", MOD_ID);
        PolyglotDispatch.call("python", STATE_SCRIPT, "prime");
        ClientTickEvents.END_CLIENT_TICK.register(
            client -> PolyglotDispatch.call("python", STATE_SCRIPT, "on_client_tick", client)
        );
    }

    public static GpuBuffer upgradeBuffer(GpuBuffer old, String name, ByteBuffer initial) {
        int usage = old.usage() | GpuBuffer.USAGE_COPY_DST;
        GpuBuffer replacement = RenderSystem.getDevice().createBuffer(() -> name, usage, initial);
        old.close();
        return replacement;
    }
}
