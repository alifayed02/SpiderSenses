#version 330

uniform sampler2D InSampler;

layout(std140) uniform ZoomBlurConfig {
    float Strength;
    float _pad1;
    float _pad2;
    float _pad3;
};

in vec2 texCoord;

out vec4 fragColor;

float random(float seed) {
    return fract(sin(dot(gl_FragCoord.xyz + seed, vec3(12.9898, 78.233, 151.7182))) * 43758.5453 + seed);
}

void main() {
    if (Strength <= 0.001) {
        fragColor = texture(InSampler, texCoord);
        return;
    }

    vec2 center = vec2(0.5, 0.5);
    vec2 toCenter = center - texCoord;
    float distFromCenter = length(toCenter);

    // Protect the center so blur kicks in gradually toward the edges.
    // Inside ~30% of the screen from center: no blur. Past ~75%: full blur.
    float edgeMask = smoothstep(0.18, 0.45, distFromCenter);
    float effective = Strength * edgeMask;

    if (effective <= 0.001) {
        fragColor = texture(InSampler, texCoord);
        return;
    }

    vec4 color = vec4(0.0);
    float total = 0.0;
    float offset = random(0.0);

    for (int i = 0; i < 40; i++) {
        float t = float(i);
        float percent = (t + offset) / 40.0;
        float weight = 4.0 * (percent - percent * percent);
        vec4 samp = texture(InSampler, texCoord + toCenter * percent * effective);
        samp.rgb *= samp.a;
        color += samp * weight;
        total += weight;
    }

    color /= total;
    color.rgb /= color.a + 0.00001;
    fragColor = color;
}
