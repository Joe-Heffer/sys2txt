# CLI reference

| Flag | Meaning |
| --- | --- |
| `--source <pulse_source_name>` | Explicit PulseAudio/PipeWire source (e.g., `alsa_output.pci-0000_00_1f.3.analog-stereo.monitor`) |
| `--list-sources` | List available Pulse sources and exit |
| `--model <size>` | Any Whisper model size accepted by the engine, e.g. `tiny\|base\|small\|medium\|large-v2`, optionally suffixed `.en` for an English-only model (default: `small.en`). `--language` auto-detection is meaningless with an `.en` model, since it only ever transcribes English |
| `--engine <auto\|faster\|whisper\|cpp>` | Force a specific engine (default: `auto`) |
| `--device <auto\|cpu\|vulkan\|gpu\|cuda>` | Device for transcription (default: `auto`). `cuda` applies to the Python engines (`faster`, `whisper`), `vulkan`/`gpu` to `cpp`; `auto` reads `SYS2TXT_DEVICE`, else CPU |
| `--language <code>` | Force language code (e.g., `en`). Omit to auto-detect |
| `--format <txt\|srt\|vtt\|json\|tsv>` | Transcript format (default: `txt`). See [Output formats](output-formats.md) |
| `--output <path>` | Also write the transcript to a file. Without it, the transcript is only printed to stdout (redirect it yourself with `>` if you want a file). In live mode `txt` appends to an existing file; the timed formats replace it, since a subtitle or JSON document cannot resume mid-file |
| `--duration <seconds>` | (once mode) Record fixed duration instead of waiting for Ctrl-C |
| `--segment-seconds <n>` | (live mode) Segment length in seconds (default: 8) |
| `--silence-timeout <seconds>` | (live mode) Stop automatically after N consecutive seconds of silence (0=disabled, default: 0). Segments that fail to transcribe do not count as silence |
| `--max-lag <seconds>` | (live mode) Untranscribed audio to tolerate before `--on-lag` applies (0=unlimited, default: 0). See [Live mode](live-mode.md) |
| `--on-lag <drop\|fail>` | (live mode) What to do once the backlog passes `--max-lag`: drop the oldest audio to catch up, or stop with an error (default: `drop`). Requires `--max-lag` |
| `--timestamps` | Print timestamps alongside text (plain text only; the timed formats always carry their own) |
| `--input <path>` | Transcribe an existing audio file instead of recording |
| `--model-path <path>` | Path to a whisper.cpp model file (for the `cpp` engine) |
| `--whisper-cpp-path <path>` | Path to the `whisper-cli` binary (for the `cpp` engine) |
| `--no-download` | Don't auto-download a missing whisper.cpp model file (for the `cpp` engine) |
| `--verbose` / `-v` | Enable debug logging |
| `--quiet` / `-q` | Suppress informational log messages (warnings and errors still show) |
