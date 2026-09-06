# Installation

## Prerequisites

- Modern linux distribution with PulseAudio or PipeWire (default on modern Ubuntu)
- ffmpeg
- Python 3.10+

## Install

1) System packages

```bash
sudo apt update
sudo apt install -y ffmpeg pipx
pipx ensurepath
```

2) Install sys2txt from [PyPI](https://pypi.org/project/sys2txt/) with [pipx](https://pipx.pypa.io/), which installs the CLI into its own isolated environment automatically (no manual venv needed):

```bash
pipx install "sys2txt[faster]"   # faster-whisper (recommended, best for CPU and NVIDIA)
pipx install "sys2txt[openai]"   # openai-whisper (reference implementation)
pipx install "sys2txt[all]"      # install both engines
pipx install sys2txt             # no Python engine (use whisper.cpp instead)
```

The tool auto-selects `faster-whisper` when available, falls back to `openai-whisper`, then falls back to `whisper.cpp`.

??? note "Alternative: install into a virtual environment"

    If you're contributing to sys2txt or want it installed into a shared/managed environment instead of pipx's isolated one:

    ```bash
    sudo apt install -y python3-venv python3-pip
    python3 -m venv .venv
    source .venv/bin/activate
    pip install sys2txt[faster]   # or [openai], [all], or no extras
    ```

**AMD GPU (or other non-CUDA GPU)?** `faster-whisper`/`openai-whisper` only accelerate on CPU or
NVIDIA CUDA — skip the extras above (`pip install sys2txt` with no extras is enough) and use the
`whisper.cpp` + Vulkan backend instead; see [Engines & devices](engines-and-devices.md#amd-gpu-vulkan).
