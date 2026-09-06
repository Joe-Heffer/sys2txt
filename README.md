# System audio to text

[![CI](https://github.com/Joe-Heffer/sys2txt/actions/workflows/ci.yml/badge.svg)](https://github.com/Joe-Heffer/sys2txt/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/sys2txt.svg)](https://badge.fury.io/py/sys2txt)
![Coverage](badge.svg)

Record system audio and automatically transcribe to text using ✨AI✨.

**Full documentation:** [oe-Heffer.github.io/sys2txt/](https://Joe-Heffer.github.io/sys2txt/)

🐞 Submit a **[bug report](https://github.com/Joe-Heffer/sys2txt/issues/new?template=bug_report.yml)**.

## Overview

`sys2txt` is a command-line tool that records your system audio (via PulseAudio/PipeWire monitor sources) with `ffmpeg` and transcribes it locally using [Whisper](https://github.com/openai/whisper). It supports both:

- On-demand: Record until you stop, then transcribe once
- Live-ish: Segment the recording every *N* seconds and transcribe each segment as it’s created (prints continuously)

You can use any of three transcription engines:
- [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) - Default, best for CPU and NVIDIA GPUs
- `openai-whisper` - Reference Python implementation
- [`whisper.cpp`](https://github.com/ggerganov/whisper.cpp) - C++ implementation with Vulkan GPU support for AMD GPUs

The tool auto-selects the first engine that is installed, preferring `faster-whisper` for its speed,
then `openai-whisper`, then `whisper.cpp`. With none of them installed it says so, rather than
failing part-way through one of them.

## Installation

```bash
sudo apt update
sudo apt install -y ffmpeg pipx
pipx ensurepath
pipx install "sys2txt[faster]"
```

See [Installation](https://Joe-Heffer.github.io/sys2txt/installation/) for the venv alternative and AMD GPU notes.

## Quick start

Record and transcribe once (press Ctrl-C to stop recording):

```bash
sys2txt once --model small.en
```

Live segmented transcription (prints ongoing transcript every 8s by default; Ctrl-C to stop):

```bash
sys2txt live --model small.en --segment-seconds 8
```

For the full flag reference, engine/device selection, live-mode lag handling, output formats,
more examples, the Python API and AMD/Vulkan setup, see the
**[documentation site](https://Joe-Heffer.github.io/sys2txt/)**.

## Contributing

Contributions are welcome! Please submit a [bug report](https://github.com/Joe-Heffer/sys2txt/issues/new?template=bug_report.yml) if you encounter any problems.

Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup and workflow
- Running tests and code quality checks
- Release process and CI/CD workflows
- Pull request guidelines

For security issues, please see [SECURITY.md](SECURITY.md).
