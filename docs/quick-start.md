# Quick start

Record and transcribe once (press Ctrl-C to stop recording):

```bash
sys2txt once --model small.en
```

Live segmented transcription (prints ongoing transcript every 8s by default; Ctrl-C to stop):

```bash
sys2txt live --model small.en --segment-seconds 8
```

For the full flag list see [CLI reference](cli-reference.md).

## Environment variables

- `SYS2TXT_DEVICE` - Default for `--device` (`cpu`, `cuda`, `vulkan`, `gpu`)
- `SYS2TXT_WHISPER_CPP` - Path to the `whisper-cli` binary, used when `--whisper-cpp-path` is omitted
- `SYS2TXT_WHISPER_CPP_MODELS` - Directory containing whisper.cpp model files, used when `--model-path` is omitted
- `SYS2TXT_WHISPER_MODEL` - Default for `--model` (falls back to `small.en`)
- `SYS2TXT_LOG_LEVEL` - Used when neither `--verbose` nor `--quiet` is given, otherwise the flag wins (e.g. `DEBUG`, `INFO`, `WARNING`)
