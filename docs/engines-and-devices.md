# Engines & devices

sys2txt supports three transcription engines, selected with `--engine` (default `auto`):

- [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) (`faster`) - Default, best for CPU and NVIDIA GPUs
- `openai-whisper` (`whisper`) - Reference Python implementation
- [`whisper.cpp`](https://github.com/ggerganov/whisper.cpp) (`cpp`) - C++ implementation with Vulkan GPU support for AMD GPUs

`auto` picks the first installed engine in that order, and says so if none are installed rather than
failing part-way through one of them.

`--device <auto|cpu|vulkan|gpu|cuda>` selects the compute device (default `auto`). `cuda` applies to the
Python engines (`faster`, `whisper`); `vulkan`/`gpu` apply to `cpp`. `auto` reads `SYS2TXT_DEVICE`, else CPU.

## AMD GPU (Vulkan)

For AMD GPUs (or other GPUs not supported by CUDA), you can use whisper.cpp with Vulkan acceleration, which is substantially faster than CPU-only transcription (the exact speedup depends on your GPU and model size).

sys2txt drives `whisper-cli` with `-oj`/`-of` and reads back its structured JSON output rather than
scraping the console's human-readable timestamps, so any `whisper-cli` build with `-oj` support works;
this has been present since well before Vulkan support was added, so a build following the instructions
below is sufficient.

### Build whisper.cpp with Vulkan

```bash
# Install Vulkan SDK
sudo apt install libvulkan-dev vulkan-tools

# Clone and build whisper.cpp
git clone https://github.com/ggerganov/whisper.cpp.git
cd whisper.cpp
cmake -B build -DGGML_VULKAN=1
cmake --build build --config Release
```

### Download models

sys2txt downloads a missing model automatically the first time it's needed, saving it to
`SYS2TXT_WHISPER_CPP_MODELS` (or `~/.local/share/whisper.cpp/models` by default). Pass `--no-download`
to disable this and fail instead, or fetch a model yourself:

```bash
# Download a model (e.g., small)
./models/download-ggml-model.sh small

# Or manually download to default location
mkdir -p ~/.local/share/whisper.cpp/models
wget -O ~/.local/share/whisper.cpp/models/ggml-small.bin \
  https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.bin
```

### Usage with whisper.cpp

```bash
# Using explicit paths
sys2txt once --engine cpp --model small \
  --whisper-cpp-path /path/to/whisper.cpp/build/bin/whisper-cli \
  --model-path /path/to/whisper.cpp/models/ggml-small.bin

# Or set environment variables
export SYS2TXT_WHISPER_CPP=/path/to/whisper-cli
export SYS2TXT_WHISPER_CPP_MODELS=/path/to/models

sys2txt once --engine cpp --model small

# Force CPU-only (disable GPU)
sys2txt once --engine cpp --model small --device cpu

# Live mode on an AMD GPU with Vulkan
sys2txt live --engine cpp --device vulkan --model small.en
```
