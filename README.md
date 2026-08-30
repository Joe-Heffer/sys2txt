# System audio to text

[![CI](https://github.com/Joe-Heffer/sys2txt/actions/workflows/ci.yml/badge.svg)](https://github.com/Joe-Heffer/sys2txt/actions/workflows/ci.yml)
[![PyPI version](https://badge.fury.io/py/sys2txt.svg)](https://badge.fury.io/py/sys2txt)

Record system audio and automatically transcribe to text using ✨AI✨.

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

### Prerequisites

- Modern linux distribution with PulseAudio or PipeWire (default on modern Ubuntu)
- ffmpeg
- Python 3.10+ (recommended)

### Install

1) System packages

```bash
sudo apt update
sudo apt install -y ffmpeg python3-venv python3-pip
```

2) Create a virtual environment and install sys2txt from [PyPI](https://pypi.org/project/sys2txt/)

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install with your preferred engine:

```bash
pip install sys2txt[faster]   # faster-whisper (recommended, best for CPU and NVIDIA)
pip install sys2txt[openai]   # openai-whisper (reference implementation)
pip install sys2txt[all]      # install both engines
pip install sys2txt           # no Python engine (use whisper.cpp instead)
```

The tool auto-selects `faster-whisper` when available, falls back to `openai-whisper`, then falls back to `whisper.cpp`.

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
- `--device <auto|cpu|vulkan|gpu|cuda>` - Device for transcription (default: auto). `cuda` applies to the
  Python engines (`faster`, `whisper`), `vulkan`/`gpu` to `cpp`; `auto` reads `SYS2TXT_DEVICE`, else CPU
- `--language <code>` - Force language code (e.g., en). Omit to auto-detect
- `--format <txt|srt|vtt|json|tsv>` - Transcript format (default: txt). See [Output formats](#output-formats)
- `--output <path>` - Write the transcript to a file. Without it, one is written to
  `./output/<timestamp>.<ext>`. In live mode `txt` appends to an existing file; the timed formats
  replace it, since a subtitle or JSON document cannot resume mid-file
- `--duration <seconds>` - (once mode) Record fixed duration instead of waiting for Ctrl-C
- `--segment-seconds <n>` - (live mode) Segment length in seconds (default: 8)
- `--silence-timeout <seconds>` - (live mode) Stop automatically after N consecutive seconds of silence (0=disabled, default: 0). Segments that fail to transcribe do not count as silence
- `--timestamps` - Print timestamps alongside text (plain text only; the timed formats always carry
  their own)

### Output formats

`--format` picks how the transcript is written, and applies to stdout and the output file alike.

| Format | Extension | What it is |
| --- | --- | --- |
| `txt` | `.txt` | Plain text, the default. One line per segment in live mode |
| `srt` | `.srt` | [SubRip](https://en.wikipedia.org/wiki/SubRip) subtitles, understood by essentially every video player |
| `vtt` | `.vtt` | [WebVTT](https://www.w3.org/TR/webvtt1/), the W3C standard, loadable by a browser `<track>` element |
| `json` | `.json` | openai-whisper's JSON schema (`text`, `segments`, `language`), for programmatic use |
| `tsv` | `.tsv` | Tab-separated `start`/`end` milliseconds and text |

The timed formats carry the engine's own per-utterance timings. In live mode those are rebased onto
the timeline of the whole recording, so cue times keep increasing across segments.

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

Produce subtitles for a recording, ready to drop next to a video:

```bash
sys2txt once --input talk.wav --format srt --output talk.srt
sys2txt once --input talk.wav --format vtt --output talk.vtt
```

Capture a meeting live as WebVTT, stopping after 30 seconds of silence:

```bash
sys2txt live --format vtt --silence-timeout 30 --output meeting.vtt
```

Get machine-readable output with per-segment timings:

```bash
sys2txt once --input talk.wav --format json --output talk.json
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

## Use as a Python library

`sys2txt` is importable as well as runnable. The library records and transcribes; printing, saving
and when to stop are yours.

Transcribe a fixed recording:

```python
from sys2txt import TranscriptionConfig, get_default_monitor_source, transcribe_once

config = TranscriptionConfig(model="small.en")
text = transcribe_once(get_default_monitor_source(), config, duration=30)
```

Consume a live recording segment by segment. `transcribe_live()` is a generator: it records until you
stop iterating, and breaking out of the loop shuts ffmpeg down and cleans up its temporary files.

```python
from sys2txt import TranscriptionConfig, get_default_monitor_source, transcribe_live

config = TranscriptionConfig(model="small.en")
for segment in transcribe_live(get_default_monitor_source(), config, segment_seconds=8):
    print(f"[{segment.start:.0f}s] {segment.text}")
    if "goodbye" in segment.text.lower():
        break
```

A segment whose transcription fails or times out is yielded with empty `text`, an `error` describing
the failure (`segment.failed` is `True`) and a warning in the log, so a failure never stops the stream
and is never mistaken for silence. A segment that times out does not hold up the ones after it: its
worker is abandoned and the next segment is transcribed on a fresh one.

To handle the audio yourself, `iter_audio_segments()` yields `AudioSegment(index, path)` values without
transcribing them, and `transcribe_file(path, config)` transcribes any audio file. Nothing in the library
prints or writes files, and every module logs through the standard `logging` module under the `sys2txt`
logger.

For timed output, use the `_cues` variants and render them yourself. They return a `Transcript` of
`Cue(start, end, text)` values plus the detected language, which `render_transcript()` turns into any
of the output formats:

```python
from sys2txt import TranscriptionConfig, render_transcript, transcribe_file_cues

transcript = transcribe_file_cues("talk.wav", TranscriptionConfig(model="small.en"))
with open("talk.srt", "w", encoding="utf-8") as f:
    f.write(render_transcript(transcript.cues, "srt"))
```

In live mode the same cues are on each `TranscriptSegment` as `segment.cues`, already rebased onto the
timeline of the recording.

The full public API is `AudioSegment`, `Cue`, `OUTPUT_FORMATS`, `Transcript`, `TranscriptSegment`,
`TranscriptionConfig`, `get_default_monitor_source`, `iter_audio_segments`, `list_pulse_sources`,
`record_once`, `render_transcript`, `transcribe_file`, `transcribe_file_cues`, `transcribe_live`,
`transcribe_once` and `transcribe_once_cues`. The package ships type hints (`py.typed`).

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
- `SYS2TXT_DEVICE`/`--device` apply to openai-whisper too, which needs a CUDA-capable PyTorch build for `cuda`.
- For AMD GPUs, use whisper.cpp with Vulkan support (see above).

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development setup and workflow
- Running tests and code quality checks
- Release process and CI/CD workflows
- Pull request guidelines

For security issues, please see [SECURITY.md](SECURITY.md).
