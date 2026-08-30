# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

sys2txt is a CLI tool for recording Ubuntu system audio (via PulseAudio/PipeWire) and transcribing it to text using Whisper models. It operates in two modes:
- **once**: Record until stopped, then transcribe once
- **live**: Segment recording every N seconds and transcribe continuously

The tool supports three transcription engines:
- **faster-whisper**: Primary engine (ctranslate2), auto-selected when available
- **openai-whisper**: Fallback reference implementation
- **whisper.cpp**: Optional C++ implementation with Vulkan GPU support for AMD GPUs

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
- `--engine {auto,faster,whisper,cpp}`: Force specific engine (default: auto)
- `--device {auto,cpu,vulkan,gpu,cuda}`: Device for transcription (default: auto)
- `--language <code>`: Force language code (e.g., en)
- `--format {txt,srt,vtt,json,tsv}`: Transcript output format (default: txt)
- `--output <path>`: Write transcript to file
- `--duration <seconds>`: (once mode) Fixed recording duration
- `--segment-seconds <n>`: (live mode) Segment length (default: 8)
- `--silence-timeout <seconds>`: (live mode) Auto-stop after N consecutive seconds of silence (0=disabled, default: 0)
- `--timestamps`: Include timestamps in output
- `--model-path <path>`: Path to whisper.cpp model file (for cpp engine)
- `--whisper-cpp-path <path>`: Path to whisper-cli binary (for cpp engine)

## Architecture

### Modular Design
The codebase is organized into focused modules by functionality:

### Core Modules

**audio.py** - Audio recording, and nothing else:
- `AudioSegment`: Frozen dataclass of `(index, path)` for one finalized chunk of recorded audio
- `record_once()`: Spawns ffmpeg subprocess to record from PulseAudio/PipeWire source to WAV file. `sample_rate`/`channels` are keyword-only and default to the constants.
- `iter_audio_segments()`: Generator. Spawns ffmpeg with the segment muxer, polls the temporary directory for finalized segments, and yields an `AudioSegment` for each. Indices are tracked by a counter (a segment holding no audio is skipped but still consumes its index). A consumer that breaks out of the loop or closes the generator triggers the `finally` that sends `q` to ffmpeg and removes the temporary directory. No transcription, no printing, no file writing.

**formats.py** - Transcript data types and output formats:
- `Cue`: Frozen dataclass of `(start, end, text)`; one timed span of speech, in seconds from the start of the recording. `shifted(offset)` moves it along the timeline
- `Transcript`: Frozen dataclass of `(cues, language)` with a `text` property that flattens the cues
- `OUTPUT_FORMATS` / `FORMAT_EXTENSIONS` / `TIMED_FORMATS`: the supported formats and their file extensions
- `format_timestamp(seconds, decimal_separator=".")`: `HH:MM:SS.mmm`, with `","` for SubRip
- `render_transcript(cues, output_format, timestamps=False, language=None)`: renders a whole document; used by once mode
- `get_formatter(output_format, ...)`: returns a `TranscriptFormatter` with `header()`/`cue()`/`footer()` for incremental rendering; used by live mode. `render_transcript` is built on it so the two paths cannot drift. The JSON formatter buffers and emits the whole document from `footer()`
- Pure formatting: no engine imports, no printing, no file writing

**pipeline.py** - Recording and transcription combined:
- `TranscriptSegment`: Frozen dataclass of `(index, text, start, end, cues, error)` with a `failed` property. `start`/`end` are the segment's fixed window on the recording clock; `cues` are the engine's own per-utterance spans, rebased onto that timeline by adding the segment's start. `error` is `None` on success and holds the reason on failure, which is what distinguishes a failed segment from a silent one (both have empty `text`).
- `transcribe_live()`: Generator over `iter_audio_segments()`, transcribing each segment on a single-worker `ThreadPoolExecutor` with a timeout. A segment that fails or times out is yielded with empty text and an `error`, and logged as a warning. A timed-out worker cannot be cancelled, so the pool is abandoned (`_new_executor()` builds a replacement) rather than letting the next segment queue behind it and time out too.
- `transcribe_once()`: Records to a temporary WAV and returns its transcript as text
- `transcribe_once_cues()`: The structured form of `transcribe_once()`, returning a `Transcript`

**pulse.py** - PulseAudio/PipeWire integration:
- `list_pulse_sources()`: Uses `pactl list short sources` to enumerate audio sources
- `get_default_monitor_source()`: Uses `pactl get-default-sink` to find default monitor source, with fallback logic to first `.monitor` source or "default"
- `run_command()`: Helper for running system commands

**engines.py** - The transcription engines and the registry that selects between them:
- `TranscriptionConfig`: Dataclass bundling engine, model, device, language, timestamps, model_path, and whisper_cpp_path. Engines take it whole; nothing destructures it into positional arguments
- `TranscriptionEngine`: `Protocol` of `name`, `is_available()`, `transcribe(path, config) -> Transcript` and `unload()`
- `_CachedModelEngine`: Base for engines that load a model. Holds the model, its key and a lock as instance state, reloading only when the key changes. One model per engine: a second would double the memory a transcription needs, and a run only ever uses one
- `FasterWhisperEngine` (`faster`): faster_whisper.WhisperModel with VAD filter, keyed on `(model, device, compute_type)`
- `OpenAIWhisperEngine` (`whisper`): `whisper.load_model(model, device=...)`, keyed on `(model, device)`
- `WhisperCppEngine` (`cpp`): Runs the whisper-cli subprocess with GPU/CPU support. Caches nothing, since the binary loads its own model
- `_resolve_device()`: `auto` reads `SYS2TXT_DEVICE` then falls back to CPU; the whisper.cpp-only GPU choices (`vulkan`, `gpu`) resolve to CPU for the Python engines
- `_resolve_whisper_cpp_binary()`: Resolves whisper-cli path from arg/env/PATH
- `_resolve_whisper_cpp_model_path()`: Resolves model path from arg/env/default
- `_parse_whisper_cpp_output()`: Parses whisper.cpp's `[HH:MM:SS.mmm --> HH:MM:SS.mmm]` lines into cues
- `ENGINES`: The registry, in the order `auto` prefers them. `ENGINE_NAMES` derives the `--engine` choices from it, so adding an engine means writing one class and adding it here
- `get_engine(name)`: `auto` returns the first engine whose `is_available()` is true, raising `RuntimeError` naming all of them if none is installed; a named engine is returned without the availability check, so the user gets that backend's own diagnostic; anything else raises `ValueError`
- Backends are imported inside the engine that needs them, so importing the package stays cheap
- Every engine returns a `Transcript`, keeping real per-utterance times; `config.timestamps` only affects plain-text rendering, which happens in `formats.py`

**transcribe.py** - The transcription entry points:
- `transcribe_file_cues(path, config)`: Asks `get_engine()` for the engine and hands it the config, returning a `Transcript` of timed `Cue` values
- `transcribe_file(path, config)`: The text form, `render_transcript(..., "txt", timestamps=config.timestamps)` over the above. Output is unchanged from before formats existed
- Re-exports `TranscriptionConfig` from `engines.py`, so `from sys2txt.transcribe import TranscriptionConfig` keeps working

**constants.py** - Configuration shared by library and CLI: default model, capture `SAMPLE_RATE`/`CHANNELS`, segment length and poll interval, minimum segment size, ffmpeg shutdown grace, transcription timeouts, `MAX_CONSECUTIVE_SEGMENT_FAILURES`, default output format.

**utils.py** - Utility functions:
- `which()`: Find command in PATH or raise RuntimeError

**__init__.py** - The public API. Exports `AudioSegment`, `Cue`, `ENGINE_NAMES`, `OUTPUT_FORMATS`, `Transcript`, `TranscriptSegment`, `TranscriptionConfig`, `TranscriptionEngine`, `get_default_monitor_source`, `iter_audio_segments`, `list_pulse_sources`, `record_once`, `render_transcript`, `transcribe_file`, `transcribe_file_cues`, `transcribe_live`, `transcribe_once`, `transcribe_once_cues` and `__version__`. Engine imports stay lazy so importing the package is cheap.

**__main__.py** - CLI entry point, and the only module that prints:
- argparse with subcommands: `once` and `live`, built by `_build_parser()`
- `Options`: Frozen dataclass; `_build_options(args)` converts the argparse `Namespace` once and validates it (missing `--input` file, non-positive `--duration`/`--segment-seconds`, `--silence-timeout` shorter than a segment), raising `ValueError` that `main()` turns into a usage error (exit 2)
- `_run_once()`: Transcribes to cues, renders them in `--format`, and prints and writes the document
- `_run_live()`: Consumes `transcribe_live()`, formatting and printing each segment, and applying the stop policies by breaking out of the loop. Plain text keeps its per-segment line format and appends to the output file; the timed formats stream a document through `get_formatter()`, opening the file for writing and emitting the footer after the loop so Ctrl-C and the silence timeout both close it. Silence is measured along the segment timeline (`segment.end` minus the start of the silent stretch), so skipped segments are accounted for. Failed segments never count as silence; `MAX_CONSECUTIVE_SEGMENT_FAILURES` of them in a row save the transcript and raise `RuntimeError`, which `main()` turns into an error and exit 1

### Key Dependencies
- **ffmpeg**: System command for audio recording (checked via shutil.which)
- **pactl**: System command for PulseAudio/PipeWire source enumeration
- **faster-whisper**: Primary transcription engine (optional, auto-detected)
- **openai-whisper**: Fallback transcription engine
- **whisper.cpp**: Optional C++ engine with Vulkan GPU support (external binary)

### GPU Acceleration

**For faster-whisper (CUDA/NVIDIA):**
- Set `SYS2TXT_DEVICE=cuda` or use `--device cuda`
- Requires compatible ctranslate2 build with CUDA support

**For whisper.cpp (Vulkan/AMD):**
- Build whisper.cpp with `-DGGML_VULKAN=1` cmake flag
- GPU is used by default; use `--device cpu` to force CPU

### Environment Variables
- `SYS2TXT_DEVICE`: Device selection for faster-whisper (`cpu`, `cuda`)
- `SYS2TXT_WHISPER_CPP`: Path to whisper-cli binary
- `SYS2TXT_WHISPER_CPP_MODELS`: Directory containing whisper.cpp model files (e.g., `ggml-small.bin`)

## Continuous Integration & Deployment

The project uses GitHub Actions for CI/CD:

### CI Workflow (`.github/workflows/ci.yml`)
Runs on:
- Push to `main` branch
- Pull requests to `main` branch

Pipeline includes:
- Testing on Python 3.9, 3.10, 3.11, and 3.12
- Code formatting check with `ruff format --check`
- Linting with `ruff check`
- Unit tests with `python -m unittest`

### Publishing Workflows

**TestPyPI** (`.github/workflows/publish-to-testpypi.yml`):
- Triggered by tags matching `v*-rc*` (e.g., `v0.1.0-rc1`)
- Publishes to https://test.pypi.org for testing
- Uses trusted publishing (no API tokens needed)

**PyPI** (`.github/workflows/publish-to-pypi.yml`):
- Triggered when a GitHub release is published
- Publishes to https://pypi.org
- Signs packages with Sigstore
- Uploads signed artifacts to GitHub release
- Uses trusted publishing (no API tokens needed)

### Setup Required for Publishing

1. **Configure Trusted Publishing on PyPI**:
   - Go to https://pypi.org/manage/account/publishing/
   - Add publisher: `Joe-Heffer/sys2txt` workflow `publish-to-pypi.yml`

2. **Configure Trusted Publishing on TestPyPI**:
   - Go to https://test.pypi.org/manage/account/publishing/
   - Add publisher: `Joe-Heffer/sys2txt` workflow `publish-to-testpypi.yml`

3. **Create environments in GitHub**:
   - Go to repository Settings → Environments
   - Create `pypi` environment
   - Create `testpypi` environment

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
- `src/sys2txt/__main__.py`: CLI entry point: parsing, validation, printing, output files, stop policy
- `src/sys2txt/audio.py`: Audio recording with ffmpeg
- `src/sys2txt/formats.py`: Transcript cues and the txt/srt/vtt/json/tsv renderers
- `src/sys2txt/pipeline.py`: Recording and transcription combined (`transcribe_live`, `transcribe_once`)
- `src/sys2txt/engines.py`: The transcription engines, the `TranscriptionEngine` protocol and the registry
- `src/sys2txt/transcribe.py`: Transcription entry points over the engine registry
- `src/sys2txt/pulse.py`: PulseAudio/PipeWire source management
- `src/sys2txt/constants.py`: Shared configuration values
- `src/sys2txt/utils.py`: Utility functions
- `src/sys2txt/__init__.py`: Public API re-exports and `__version__`
- `src/sys2txt/py.typed`: Type-hint marker (PEP 561)
- `tests/`: Unit tests for all modules (using unittest framework)
  - `tests/test_utils.py`: Tests for utility functions
  - `tests/test_pulse.py`: Tests for PulseAudio integration
  - `tests/test_transcribe.py`: Tests for the transcription entry points
  - `tests/test_engines.py`: Tests for the engines, the registry and the model cache
  - `tests/test_audio.py`: Tests for audio recording
  - `tests/test_formats.py`: Tests for the transcript output formats
  - `tests/test_pipeline.py`: Tests for the recording/transcription pipeline
  - `tests/test___main__.py`: Tests for the CLI
  - `tests/test_init.py`: Tests for the public API surface
- `.github/workflows/`:
  - `ci.yml`: CI workflow (tests, linting, formatting)
  - `publish-to-pypi.yml`: Publish to PyPI on release
  - `publish-to-testpypi.yml`: Publish to TestPyPI on RC tags
- `pyproject.toml`: Project metadata, dependencies, and build config
- `requirements.txt`: Python dependencies (faster-whisper, openai-whisper)
- `README.md`: User documentation with installation, usage, examples

## Platform Requirements
- Ubuntu (or Linux with PulseAudio/PipeWire)
- Python 3.9+
- ffmpeg
- PulseAudio or PipeWire (for monitor source capture)
