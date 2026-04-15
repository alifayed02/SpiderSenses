#version 330

uniform sampler2D InSampler;

layout(std140) uniform SharpenConfig {
    float Amount;
};

in vec2 texCoord;

out vec4 fragColor;

void main() {
    if (Amount <= 0.001) {
        fragColor = texture(InSampler, texCoord);
        return;
    }

    vec2 texelSize = 1.0 / vec2(textureSize(InSampler, 0));

    float neighbor = Amount * -1.0;
    float center   = Amount *  4.0 + 1.0;

    vec4 centerSample = texture(InSampler, texCoord);

    vec3 color =
          texture(InSampler, texCoord + vec2(          0.0,  texelSize.y)).rgb * neighbor
        + texture(InSampler, texCoord + vec2(-texelSize.x,          0.0)).rgb * neighbor
        + centerSample.rgb * center
        + texture(InSampler, texCoord + vec2( texelSize.x,          0.0)).rgb * neighbor
        + texture(InSampler, texCoord + vec2(          0.0, -texelSize.y)).rgb * neighbor;

    fragColor = vec4(color, centerSample.a);
}
