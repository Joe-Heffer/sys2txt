[![CI](https://github.com/Joe-Heffer/sys2txt/actions/workflows/ci.yml/badge.svg)](https://github.com/Joe-Heffer/sys2txt/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/sys2txt.svg)](https://badge.fury.io/py/sys2txt)
[![Python versions](https://img.shields.io/pypi/status/sys2txt.svg)](https://pypi.org/project/sys2txt/)

# System audio to text

Record system audio and automatically transcribe to text using ✨AI✨.

## Overview

`sys2txt` is a command-line tool that records your system audio (via PulseAudio/PipeWire monitor sources) with `ffmpeg` and transcribes it locally using [Whisper](https://github.com/openai/whisper). It supports both:

- On-demand: Record until you stop, then transcribe once
- Live-ish: Segment the recording every *N* seconds and transcribe each segment as it’s created (prints continuously)

You can use any of three transcription engines:
- [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) - Default, best for CPU and NVIDIA GPUs
- `openai-whisper` - Reference Python implementation
- [`whisper.cpp`](https://github.com/ggerganov/whisper.cpp) - C++ implementation with Vulkan GPU support for AMD GPUs

The tool auto-selects `faster-whisper` when available for better speed.

## Installation

### Prerequisites

- Ubuntu with PulseAudio or PipeWire (default on modern Ubuntu)
- ffmpeg
- Python 3.9+ (recommended)

### Install

1) System packages

```bash
sudo apt update
sudo apt install -y ffmpeg python3-venv python3-pip
```

2) Create a virtual environment and install sys2txt

```bash
cd sys2txt
python3 -m venv .venv
source .venv/bin/activate
pip install sys2txt
```

This installs both faster-whisper (for speed) and openai-whisper (reference implementation). The tool auto-selects faster-whisper when available or falls back to openai-whisper.

## Usage

### Quick start

Record and transcribe once (press Ctrl-C to stop recording):

```bash
sys2txt once --model small.en
```

Live segmented transcription (prints ongoing transcript every 8s by default; Ctrl-C to stop):

```bash
sys2txt live --model small.en --segment-seconds 8
```

### Useful flags

- `--source <pulse_source_name>` - Explicit PulseAudio/PipeWire source (e.g., alsa_output.pci-0000_00_1f.3.analog-stereo.monitor)
- `--list-sources` - List available Pulse sources and exit
- `--model <size>` - tiny|base|small|medium|large-v2 (default: small)
- `--engine <auto|faster|whisper|cpp>` - Force a specific engine (default: auto)
- `--device <auto|cpu|vulkan|gpu|cuda>` - Device for transcription (default: auto)
- `--language <code>` - Force language code (e.g., en). Omit to auto-detect
- `--output <path>` - Write final transcript to a file (in live mode, appends)
- `--duration <seconds>` - (once mode) Record fixed duration instead of waiting for Ctrl-C
- `--segment-seconds <n>` - (live mode) Segment length in seconds (default: 8)
- `--timestamps` - Print timestamps alongside text

## Examples

Record 30s of system audio from the default monitor and transcribe:

```bash
sys2txt once --duration 30 --model small --output transcript.txt
```

Use a specific PulseAudio source:

```bash
sys2txt once --source alsa_output.usb-Focusrite_Scarlett.monitor --model base
```

Live mode with shorter latency and timestamps:

```bash
sys2txt live --segment-seconds 5 --timestamps
```

Force the reference openai-whisper engine:

```bash
sys2txt once --engine whisper --model base
```

Transcribe an existing audio file:

```bash
sys2txt once --input recording.wav --model small
```

### Just want one-liners (no sys2txt)?

Find the default sink and its monitor source:

```bash
pactl get-default-sink
pactl list short sources | grep monitor
```

Record 30s of system audio from the default monitor to a WAV at 16 kHz mono (good for Whisper):

```bash
ffmpeg -hide_banner -loglevel error -f pulse -i "$(pactl get-default-sink).monitor" -ac 1 -ar 16000 -t 30 out.wav
```

Transcribe with openai-whisper CLI:

```bash
whisper out.wav --model small --task transcribe --language en
```

## Whisper.cpp with Vulkan GPU

For AMD GPUs (or other GPUs not supported by CUDA), you can use whisper.cpp with Vulkan acceleration for ~8x speedup over CPU.

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
```

## Tips and troubleshooting

- If you get silence, ensure you are using the monitor source for your output device (the name ends with `.monitor`). Use `--list-sources` to view options.
- Make sure the application you want to capture is playing through the same output sink as your default sink. You can manage routes with `pavucontrol`.
- PipeWire systems expose PulseAudio-compatible sources, so `-f pulse` in ffmpeg still works.
- For better performance on CPU, use faster-whisper with model `base` or `small`. For the best accuracy, use `medium` or `large-v2` (these are heavier).
- GPU acceleration for faster-whisper requires a compatible ctranslate2 CUDA wheel. Set `SYS2TXT_DEVICE=cuda` or use `--device cuda` to enable it.
- For AMD GPUs, use whisper.cpp with Vulkan support (see above).

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup and workflow
- Running tests and code quality checks
- Release process and CI/CD workflows
- Pull request guidelines

For security issues, please see [SECURITY.md](SECURITY.md).
