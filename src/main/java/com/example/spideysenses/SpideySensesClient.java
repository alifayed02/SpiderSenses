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
 * the thinnest possible shell. All state, threat tracking, envelopes, and per-tick
 * logic live in {@code src/main/scripts/state.py}; mixins are in sibling scripts.
 *
 * <p>A couple of Java-interop-heavy helpers are exposed here for Python to call —
 * the {@code Supplier<String>} argument GraalPy struggled to auto-coerce from
 * Python lambdas, and passing a {@code float[]} through is cleanest via a static
 * Java entry.</p>
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

    /**
     * Allocates a new uniform GpuBuffer with COPY_DST added to the usage flags
     * and fills it with {@code initial}. Called from Python on first write to
     * upgrade the PostPass's UBO (vanilla creates UBOs without COPY_DST, so the
     * CommandEncoder rejects writeToBuffer until it's upgraded).
     */
    public static GpuBuffer upgradeBuffer(GpuBuffer old, String name, ByteBuffer initial) {
        int usage = old.usage() | GpuBuffer.USAGE_COPY_DST;
        GpuBuffer replacement = RenderSystem.getDevice().createBuffer(() -> name, usage, initial);
        old.close();
        return replacement;
    }
}
