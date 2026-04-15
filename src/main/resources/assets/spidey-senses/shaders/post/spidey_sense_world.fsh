#version 330

uniform sampler2D MainSampler;
uniform sampler2D MainDepthSampler;

layout(std140) uniform SenseConfig {
    float Radius;
    float EdgeSoftness;
    float Strength;
    float Darkness;
    vec4 CameraPos;
    mat4 InverseViewProj;
};

in vec2 texCoord;

out vec4 fragColor;

float hash21(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float valueNoise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = hash21(i);
    float b = hash21(i + vec2(1.0, 0.0));
    float c = hash21(i + vec2(0.0, 1.0));
    float d = hash21(i + vec2(1.0, 1.0));
    return mix(mix(a, b, f.x), mix(c, d, f.x), f.y);
}

float fbm(vec2 p) {
    float v = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 4; i++) {
        v += amp * valueNoise(p);
        p *= 2.03;
        amp *= 0.5;
    }
    return v;
}

void main() {
    vec3 baseColor = texture(MainSampler, texCoord).rgb;

    if (Strength <= 0.001) {
        fragColor = vec4(baseColor, 1.0);
        return;
    }

    float depth = texture(MainDepthSampler, texCoord).r;
    if (depth >= 1.0) {
        fragColor = vec4(baseColor, 1.0);
        return;
    }

    vec4 ndc = vec4(texCoord * 2.0 - 1.0, depth * 2.0 - 1.0, 1.0);
    vec4 worldH = InverseViewProj * ndc;
    vec3 worldPos = worldH.xyz / worldH.w;

    float dist = distance(worldPos, CameraPos.xyz);

    float edgeNoise = (hash21(floor(worldPos.xz * 2.0)) - 0.5) * EdgeSoftness * 1.2;
    float insideness = 1.0 - smoothstep(
        Radius - EdgeSoftness + edgeNoise,
        Radius + EdgeSoftness + edgeNoise,
        dist
    );

    if (insideness <= 0.0) {
        fragColor = vec4(baseColor, 1.0);
        return;
    }

    float relX = worldPos.x - CameraPos.x;
    float splitX = smoothstep(-6.0, 6.0, relX);

    // World-stable noise drives region shape.
    float noise = fbm(worldPos.xz * 0.08 + vec2(worldPos.y * 0.05, 0.0));

    // Raw depth-buffer banding. The depth buffer is exponentially non-linear,
    // so this produces tight rings near the player that widen with distance.
    float rawDepthPattern = 0.5 + 0.5 * sin(depth * 120.0);

    float rawSplit = clamp(
          0.55 * noise
        + 0.35 * rawDepthPattern
        + 0.10 * splitX,
        0.0, 1.0);

    // Narrow smoothstep pushes the factor toward 0 or 1, so pixels commit
    // to mostly-red or mostly-blue with only a thin transition band.
    float split = smoothstep(0.45, 0.55, rawSplit);

    vec3 tintLeft  = vec3(0.25, 0.55, 1.00);
    vec3 tintRight = vec3(1.00, 0.30, 0.35);
    vec3 tint = mix(tintLeft, tintRight, split);

    // Filter-style: rebuild the pixel from the tint modulated by luminance.
    // The underlying framebuffer is already lifted by the night-vision mixin
    // when the effect is active, so no in-shader brightness compensation needed.
    float lum = dot(baseColor, vec3(0.299, 0.587, 0.114));
    vec3 sensed = mix(tint * 0.15, tint * 1.10, smoothstep(0.15, 0.85, lum));

    vec3 finalColor = mix(baseColor, sensed, clamp(insideness * Strength, 0.0, 1.0));

    fragColor = vec4(finalColor, 1.0);
}
