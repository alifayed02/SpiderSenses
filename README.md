# Spidey Senses

> spider-sense for minecraft, written in python via elide

A Fabric mod that gives the player a Spider-Man-style "spider-sense" warning.
When a hostile mob gets close to you but is approaching from outside your
view cone, the world tints red/blue, the camera nudges, and a chromatic
vignette fires. The effect cools down for thirty seconds before it can
trigger again.

The mod itself is small, and that's intentional. Its real purpose is to
**stress-test [Elide](../WHIPLASH) as a polyglot Minecraft toolchain**. All
gameplay logic is written in Python. There is no Gradle, no `build.gradle`,
no `gradle/` directory, no daemon, and almost no Java in the source tree.

## Structure

- [`elide.pkl`](./elide.pkl) - Project manifest; replaces `build.gradle`
- [`src/main/java`](./src/main/java) - Fabric client entrypoint and one `GpuBuffer` helper
- [`src/main/scripts`](./src/main/scripts) - All gameplay and mixin logic, in Python
- [`src/main/resources`](./src/main/resources) - `fabric.mod.json`, post-effect chain definitions, and GLSL shaders

### Python Modules

- [`state.py`](./src/main/scripts/state.py) - Threat tracking, envelope curves, per-tick logic, uniform pushes
- [`accessors.py`](./src/main/scripts/accessors.py) - `@mixin.accessor` and `@mixin.invoker` stubs
- [`camera_fov.py`](./src/main/scripts/camera_fov.py) - FOV warp mixin
- [`lightmap.py`](./src/main/scripts/lightmap.py) - Night-vision lift mixin
- [`level_renderer.py`](./src/main/scripts/level_renderer.py) - World-space post-effect dispatch mixin

## Why Elide

[Elide](https://elide.dev) is a single-binary build system and polyglot
runtime that, for this project, replaces the entire Gradle stack:

- **No Gradle.** The project manifest is six lines of `elide.pkl`. No buildscript, no plugins, no daemon.
- **~20× faster Java compilation** than stock `javac`, with a JDK bundled in the binary, so no separate install or `JAVA_HOME` to manage.
- **Polyglot mixins.** Mixin definitions and gameplay logic are written in Python. Java in this repo is a thin entrypoint.

See [elide.dev](https://elide.dev) for the actual story.

## Availability

> [!NOTE]
> Coming to [Modrinth](https://modrinth.com) soon.
