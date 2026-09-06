# System audio to text

[![CI](https://github.com/Joe-Heffer/sys2txt/actions/workflows/ci.yml/badge.svg)](https://github.com/Joe-Heffer/sys2txt/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/sys2txt.svg)](https://badge.fury.io/py/sys2txt)

Record system audio and automatically transcribe to text using ✨AI✨.

## Overview

`sys2txt` is a command-line tool that records your system audio (via PulseAudio/PipeWire monitor sources) with `ffmpeg` and transcribes it locally using [Whisper](https://github.com/openai/whisper). It supports both:

- On-demand: Record until you stop, then transcribe once
- Live-ish: Segment the recording every *N* seconds and transcribe each segment as it's created (prints continuously)

You can use any of three transcription engines:

- [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) - Default, best for CPU and NVIDIA GPUs
- `openai-whisper` - Reference Python implementation
- [`whisper.cpp`](https://github.com/ggerganov/whisper.cpp) - C++ implementation with Vulkan GPU support for AMD GPUs

The tool auto-selects the first engine that is installed, preferring `faster-whisper` for its speed,
then `openai-whisper`, then `whisper.cpp`. With none of them installed it says so, rather than
failing part-way through one of them.

See [Installation](installation.md) to get started, or jump straight to [Quick start](quick-start.md).
