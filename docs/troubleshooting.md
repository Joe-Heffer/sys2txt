# Tips and troubleshooting

- If you get silence, ensure you are using the monitor source for your output device (the name ends with `.monitor`). Use `--list-sources` to view options.
- Make sure the application you want to capture is playing through the same output sink as your default sink. You can manage routes with `pavucontrol`.
- PipeWire systems expose PulseAudio-compatible sources, so `-f pulse` in ffmpeg still works.
- For better performance on CPU, use faster-whisper with model `base` or `small`. For the best accuracy, use `medium` or `large-v2` (these are heavier).
- GPU acceleration for faster-whisper requires a compatible ctranslate2 CUDA wheel. Set `SYS2TXT_DEVICE=cuda` or use `--device cuda` to enable it.
- `SYS2TXT_DEVICE`/`--device` apply to openai-whisper too, which needs a CUDA-capable PyTorch build for `cuda`.
- For AMD GPUs, use whisper.cpp with Vulkan support (see [Engines & devices](engines-and-devices.md#amd-gpu-vulkan)).

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](https://github.com/Joe-Heffer/sys2txt/blob/main/CONTRIBUTING.md) for:

- Development setup and workflow
- Running tests and code quality checks
- Release process and CI/CD workflows
- Pull request guidelines

For security issues, please see [SECURITY.md](https://github.com/Joe-Heffer/sys2txt/blob/main/SECURITY.md).
