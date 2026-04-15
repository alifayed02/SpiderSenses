package com.example.spideysenses;

import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.monster.Enemy;

public class ThreatTracker {
    private final double detectionRadius;
    private final double detectionRadiusSqr;
    private volatile float threat = 0.0f;

    public ThreatTracker(double detectionRadius) {
        this.detectionRadius = detectionRadius;
        this.detectionRadiusSqr = detectionRadius * detectionRadius;
    }

    public void tick(Minecraft client) {
        LocalPlayer player = client.player;
        ClientLevel level = client.level;
        if (player == null || level == null || client.isPaused()) {
            decay();
            return;
        }

        double closestSqr = Double.MAX_VALUE;
        for (Entity entity : level.entitiesForRendering()) {
            if (!(entity instanceof Enemy)) continue;
            if (!entity.isAlive()) continue;
            double distSqr = entity.distanceToSqr(player);
            if (distSqr < closestSqr) {
                closestSqr = distSqr;
            }
        }

        float target;
        if (closestSqr >= detectionRadiusSqr) {
            target = 0.0f;
        } else {
            double dist = Math.sqrt(closestSqr);
            target = (float) (1.0 - dist / detectionRadius);
        }

        float smoothing = target > threat ? 0.25f : 0.08f;
        threat = threat + (target - threat) * smoothing;
    }

    private void decay() {
        threat *= 0.9f;
        if (threat < 0.001f) threat = 0.0f;
    }

    public float level() {
        return threat;
    }
}
