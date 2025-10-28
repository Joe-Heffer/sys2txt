# sys2txt

Record system audio and transcribe to text using AI.

## Overview

sys2txt is a tiny CLI that records your Ubuntu system audio (via PulseAudio/PipeWire monitor sources) with ffmpeg and transcribes it locally using Whisper. It supports both:

- On-demand: Record until you stop, then transcribe once
- Live-ish: Segment the recording every N seconds and transcribe each segment as it’s created (prints continuously)

You can use either the openai-whisper (Python) reference implementation or the faster-whisper (ctranslate2) engine if installed. The tool auto-selects faster-whisper when available for better speed on CPU and especially GPU.

## Installation

### Prerequisites

- Ubuntu with PulseAudio or PipeWire (default on modern Ubuntu)
- ffmpeg
- Python 3.9+ (recommended)

### Install

1) System packages

```bash
sudo apt update && sudo apt install -y ffmpeg python3-venv python3-pip
```

2) Create a virtual environment and install Python deps

```bash
cd /workspace/sys2txt
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

By default, this installs faster-whisper for speed. If you prefer the reference implementation, it also installs openai-whisper, and sys2txt will use faster-whisper when present or fall back to openai-whisper.

## Quick start

- Record and transcribe once (press Ctrl-C to stop recording):

```bash
source .venv/bin/activate
python sys2txt.py once --model small
```

- Live segmented transcription (prints ongoing transcript every 8s by default; Ctrl-C to stop):

    python sys2txt.py live --model small --segment-seconds 8

Useful flags

- --source <pulse_source_name>  Explicit PulseAudio/PipeWire source (e.g., alsa_output.pci-0000_00_1f.3.analog-stereo.monitor)
- --list-sources                 List available Pulse sources and exit
- --model <size>                 tiny|base|small|medium|large-v2 (default: small)
- --engine <auto|faster|whisper> Force a specific engine (default: auto)
- --language <code>              Force language code (e.g., en). Omit to auto-detect
- --output <path>                Write final transcript to a file (in live mode, appends)
- --duration <seconds>           (once mode) Record fixed duration instead of waiting for Ctrl-C
- --segment-seconds <n>          (live mode) Segment length in seconds (default: 8)
- --timestamps                   Print timestamps alongside text

## Examples

1) Record 30s of system audio from the default monitor and transcribe with faster-whisper:

    python sys2txt.py once --duration 30 --model small --output transcript.txt

2) Use a specific PulseAudio source:

    python sys2txt.py once --source alsa_output.usb-Focusrite_Scarlett.monitor --model base

3) Live mode with shorter latency and timestamps:

    python sys2txt.py live --segment-seconds 5 --timestamps

4) Force the reference openai-whisper engine:

    python sys2txt.py once --engine whisper --model base

Just want one-liners (no sys2txt)?

- Find the default sink and its monitor source:

    pactl get-default-sink
    pactl list short sources | grep monitor

- Record 30s of system audio from the default monitor to a WAV at 16 kHz mono (good for Whisper):

    ffmpeg -hide_banner -loglevel error -f pulse -i "$(pactl get-default-sink).monitor" -ac 1 -ar 16000 -t 30 out.wav

- Transcribe with openai-whisper CLI:

    whisper out.wav --model small --task transcribe --language en

## Tips and troubleshooting

- If you get silence, ensure you are using the monitor source for your output device (the name ends with .monitor). Use --list-sources to view options.
- Make sure the application you want to capture is playing through the same output sink as your default sink. You can manage routes with pavucontrol.
- PipeWire systems expose PulseAudio-compatible sources, so -f pulse in ffmpeg still works.
- For better performance on CPU, use faster-whisper with model base or small. For the best accuracy, use medium or large-v2 (these are heavier).
- GPU acceleration for faster-whisper requires a compatible ctranslate2 CUDA wheel. If not available, it will run on CPU.
