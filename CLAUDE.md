# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

sys2txt is a CLI tool for recording Ubuntu system audio (via PulseAudio/PipeWire) and transcribing it to text using Whisper models. It operates in two modes:
- **once**: Record until stopped, then transcribe once
- **live**: Segment recording every N seconds and transcribe continuously

The tool automatically selects faster-whisper (ctranslate2) for better performance when available, falling back to openai-whisper if not.

## Development Setup

1. Install system dependencies:
```bash
sudo apt update && sudo apt install -y ffmpeg python3-venv python3-pip
```

2. Create virtual environment and install Python dependencies:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running the Application

The main entry point is `src/sys2txt/__main__.py`. After installing with `pip install -e .`, use the `sys2txt` command:

```bash
# Activate virtual environment first
source .venv/bin/activate

# Install in editable mode
pip install -e .

# Once mode - record and transcribe once
sys2txt once --model small

# Live mode - continuous segmented transcription
sys2txt live --model small --segment-seconds 8

# List available PulseAudio sources
sys2txt once --list-sources

# Transcribe existing audio file without recording
sys2txt once --input audio.wav --model small
```

Alternatively, run as a module without installing: `python -m sys2txt once --model small`

Common flags:
- `--source <name>`: Specify PulseAudio/PipeWire source (e.g., `alsa_output.pci-0000_00_1f.3.analog-stereo.monitor`)
- `--model {tiny,base,small,medium,large-v2}`: Whisper model size (default: small)
- `--engine {auto,faster,whisper}`: Force specific engine (default: auto)
- `--language <code>`: Force language code (e.g., en)
- `--output <path>`: Write transcript to file
- `--duration <seconds>`: (once mode) Fixed recording duration
- `--segment-seconds <n>`: (live mode) Segment length (default: 8)
- `--timestamps`: Include timestamps in output

## Architecture

### Modular Design
The codebase is organized into focused modules by functionality:

### Core Modules

**audio.py** - Audio recording functionality:
- `record_once()`: Spawns ffmpeg subprocess to record from PulseAudio/PipeWire source to WAV file at 16 kHz mono
- `segment_and_transcribe_live()`: Spawns ffmpeg with segment muxer to create sequential WAV files, monitors temporary directory for new segments, and calls transcribe callback for each. Uses stdin 'q' command for graceful ffmpeg shutdown on Ctrl-C.

**pulse.py** - PulseAudio/PipeWire integration:
- `list_pulse_sources()`: Uses `pactl list short sources` to enumerate audio sources
- `get_default_monitor_source()`: Uses `pactl get-default-sink` to find default monitor source, with fallback logic to first `.monitor` source or "default"
- `run_command()`: Helper for running system commands

**transcribe.py** - Whisper transcription:
- `transcribe_file()`: Auto-selects engine (faster-whisper preferred, openai-whisper fallback)
- `_transcribe_faster_whisper()`: Uses faster_whisper.WhisperModel with VAD filter, device selection via SYS2TXT_DEVICE env var (default: CPU int8)
- `_transcribe_openai_whisper()`: Uses whisper.load_model() and model.transcribe()
- Both support timestamps flag for per-segment timing output

**utils.py** - Utility functions:
- `which()`: Find command in PATH or raise RuntimeError

**__main__.py** - CLI entry point:
- argparse with subcommands: `once` and `live`
- Common parent parser for shared arguments
- Mode dispatch logic and transcribe callback creation for live mode

### Key Dependencies
- **ffmpeg**: System command for audio recording (checked via shutil.which)
- **pactl**: System command for PulseAudio/PipeWire source enumeration
- **faster-whisper**: Primary transcription engine (optional, auto-detected)
- **openai-whisper**: Fallback transcription engine

### GPU Acceleration
Set `SYS2TXT_DEVICE=cuda` environment variable to enable CUDA acceleration for faster-whisper (requires compatible ctranslate2 build with CUDA support).

## Continuous Integration

The project uses GitHub Actions for CI/CD. The workflow (`.github/workflows/ci.yml`) runs on:
- Push to `main` branch
- Pull requests to `main` branch

CI pipeline includes:
- Testing on Python 3.9, 3.10, 3.11, and 3.12
- Code formatting check with `ruff format --check`
- Linting with `ruff check`
- Unit tests with `python -m unittest`

## Development Commands

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run unit tests
python -m unittest discover -s tests -p "test_*.py"

# Run unit tests with verbose output
python -m unittest discover -s tests -p "test_*.py" -v

# Run a specific test file
python -m unittest tests/test_audio.py

# Run a specific test class
python -m unittest tests.test_audio.TestRecordOnce

# Format code with ruff
ruff format src/

# Lint code
ruff check src/

# Auto-fix linting issues
ruff check --fix src/
```

## File Structure
- `src/sys2txt/__main__.py`: CLI entry point (~130 lines)
- `src/sys2txt/audio.py`: Audio recording with ffmpeg
- `src/sys2txt/transcribe.py`: Whisper transcription engines
- `src/sys2txt/pulse.py`: PulseAudio/PipeWire source management
- `src/sys2txt/utils.py`: Utility functions
- `src/sys2txt/__init__.py`: Empty package marker
- `tests/`: Unit tests for all modules (using unittest framework)
  - `tests/test_utils.py`: Tests for utility functions
  - `tests/test_pulse.py`: Tests for PulseAudio integration
  - `tests/test_transcribe.py`: Tests for transcription engines
  - `tests/test_audio.py`: Tests for audio recording
- `.github/workflows/ci.yml`: GitHub Actions CI/CD workflow
- `pyproject.toml`: Project metadata, dependencies, and build config
- `requirements.txt`: Python dependencies (faster-whisper, openai-whisper)
- `README.md`: User documentation with installation, usage, examples

## Platform Requirements
- Ubuntu (or Linux with PulseAudio/PipeWire)
- Python 3.9+
- ffmpeg
- PulseAudio or PipeWire (for monitor source capture)
