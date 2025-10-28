# sys2txt

[![CI](https://github.com/Joe-Heffer/sys2txt/actions/workflows/ci.yml/badge.svg)](https://github.com/Joe-Heffer/sys2txt/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/sys2txt.svg)](https://badge.fury.io/py/sys2txt)
[![Python versions](https://img.shields.io/pypi/pyversions/sys2txt.svg)](https://pypi.org/project/sys2txt/)

Record system audio and transcribe to text using ✨AI✨.

## Overview

sys2txt is a command-line tool that records your system audio (via PulseAudio/PipeWire monitor sources) with `ffmpeg` and transcribes it locally using [Whisper](https://github.com/openai/whisper). It supports both:

- On-demand: Record until you stop, then transcribe once
- Live-ish: Segment the recording every *N* seconds and transcribe each segment as it’s created (prints continuously)

You can use either the `openai-whisper` (Python) reference implementation or the [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) engine if installed. The tool auto-selects `faster-whisper` when available for better speed on CPU and especially GPU.

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
pip install -e .
```

This installs both faster-whisper (for speed) and openai-whisper (reference implementation). The tool auto-selects faster-whisper when available or falls back to openai-whisper.

## Quick start

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
- `--engine <auto|faster|whisper>` - Force a specific engine (default: auto)
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

## Tips and troubleshooting

- If you get silence, ensure you are using the monitor source for your output device (the name ends with `.monitor`). Use `--list-sources` to view options.
- Make sure the application you want to capture is playing through the same output sink as your default sink. You can manage routes with `pavucontrol`.
- PipeWire systems expose PulseAudio-compatible sources, so `-f pulse` in ffmpeg still works.
- For better performance on CPU, use faster-whisper with model `base` or `small`. For the best accuracy, use `medium` or `large-v2` (these are heavier).
- GPU acceleration for faster-whisper requires a compatible ctranslate2 CUDA wheel. Set `SYS2TXT_DEVICE=cuda` to enable it. If not available, it will run on CPU.

## Development

Install with development dependencies:

```bash
pip install -e ".[dev]"
```

Run unit tests:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Format and lint code:

```bash
ruff format src/
ruff check src/
```
