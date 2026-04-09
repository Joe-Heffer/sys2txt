"""Transcription functionality using Whisper models."""

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Optional

# Cached model instances to avoid expensive reloads on every segment
_faster_whisper_model = None
_faster_whisper_model_key: Optional[tuple] = None
_openai_whisper_model = None
_openai_whisper_model_key: Optional[str] = None


def transcribe_file(
    path: str,
    engine: str,
    model_size: str,
    language: Optional[str],
    timestamps: bool,
    model_path: Optional[str] = None,
    whisper_cpp_path: Optional[str] = None,
    device: str = "auto",
) -> str:
    """Transcribe an audio file using the specified Whisper engine.

    Args:
        path: Path to audio file
        engine: Engine to use ("auto", "faster", "whisper", or "cpp")
        model_size: Whisper model size (tiny, base, small, medium, large-v2)
        language: Optional language code (e.g., "en"). If None, auto-detect.
        timestamps: Whether to include timestamps in output
        model_path: Path to whisper.cpp model file (for cpp engine)
        whisper_cpp_path: Path to whisper-cli binary (for cpp engine)
        device: Device to use ("auto", "cpu", "vulkan", "gpu", "cuda")

    Returns:
        Transcribed text
    """
    engine = engine.lower()
    if engine == "auto":
        try:
            import faster_whisper  # noqa: F401

            engine = "faster"
        except ImportError:
            engine = "whisper"

    if engine == "faster":
        return _transcribe_faster_whisper(path, model_size, language, timestamps, device)
    elif engine == "whisper":
        return _transcribe_openai_whisper(path, model_size, language, timestamps)
    elif engine == "cpp":
        return _transcribe_whisper_cpp(path, model_size, language, timestamps, model_path, whisper_cpp_path, device)
    else:
        raise ValueError(f"Unknown engine: {engine}")


def _transcribe_faster_whisper(
    path: str, model_size: str, language: Optional[str], timestamps: bool, device: str = "auto"
) -> str:
    """Transcribe using faster-whisper (ctranslate2 backend)."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as e:
        raise RuntimeError("faster-whisper is not installed. pip install faster-whisper") from e

    # Device selection: CLI arg > env var > default (cpu)
    if device == "auto":
        device = os.environ.get("SYS2TXT_DEVICE", "cpu")

    if device == "cuda":
        fw_device = "cuda"
        compute_type = "float16"
    else:
        fw_device = "cpu"
        compute_type = "int8"

    global _faster_whisper_model, _faster_whisper_model_key
    key = (model_size, fw_device, compute_type)
    if _faster_whisper_model_key != key:
        _faster_whisper_model = WhisperModel(model_size, device=fw_device, compute_type=compute_type)
        _faster_whisper_model_key = key
    model = _faster_whisper_model
    segments, info = model.transcribe(path, vad_filter=True, language=language)
    if timestamps:
        lines = []
        for seg in segments:
            s = f"[{seg.start:6.2f}-{seg.end:6.2f}] {seg.text.strip()}"
            lines.append(s)
        return "\n".join(lines)
    else:
        text_parts = [seg.text for seg in segments]
        return " ".join(t.strip() for t in text_parts).strip()


def _transcribe_openai_whisper(path: str, model_size: str, language: Optional[str], timestamps: bool) -> str:
    """Transcribe using openai-whisper (reference implementation)."""
    try:
        import whisper  # type: ignore
    except ImportError as e:
        raise RuntimeError("openai-whisper is not installed. pip install openai-whisper") from e

    global _openai_whisper_model, _openai_whisper_model_key
    if _openai_whisper_model_key != model_size:
        _openai_whisper_model = whisper.load_model(model_size)
        _openai_whisper_model_key = model_size
    model = _openai_whisper_model
    result = model.transcribe(path, language=language)
    if timestamps and "segments" in result:
        lines = []
        for seg in result.get("segments", []):
            start = seg.get("start", 0.0)
            end = seg.get("end", 0.0)
            text = seg.get("text", "").strip()
            lines.append(f"[{start:6.2f}-{end:6.2f}] {text}")
        return "\n".join(lines)
    else:
        return result.get("text", "").strip()


def _resolve_whisper_cpp_binary(whisper_cpp_path: Optional[str]) -> str:
    """Resolve the path to the whisper-cli binary.

    Priority:
    1. Explicit path argument
    2. SYS2TXT_WHISPER_CPP environment variable
    3. PATH lookup for 'whisper-cli'

    Args:
        whisper_cpp_path: Explicit path to whisper-cli binary

    Returns:
        Path to whisper-cli binary

    Raises:
        RuntimeError: If binary cannot be found
    """
    if whisper_cpp_path:
        if not os.path.isfile(whisper_cpp_path):
            raise RuntimeError(f"whisper-cli binary not found at: {whisper_cpp_path}")
        return whisper_cpp_path

    env_path = os.environ.get("SYS2TXT_WHISPER_CPP")
    if env_path:
        if not os.path.isfile(env_path):
            raise RuntimeError(f"whisper-cli binary not found at SYS2TXT_WHISPER_CPP: {env_path}")
        return env_path

    path_lookup = shutil.which("whisper-cli")
    if path_lookup:
        return path_lookup

    raise RuntimeError(
        "whisper-cli binary not found. Install whisper.cpp and either:\n"
        "  1. Add whisper-cli to PATH\n"
        "  2. Set SYS2TXT_WHISPER_CPP environment variable\n"
        "  3. Use --whisper-cpp-path argument"
    )


def _resolve_whisper_cpp_model_path(model_path: Optional[str], model_size: str) -> str:
    """Resolve the path to a whisper.cpp model file.

    Priority:
    1. Explicit model_path argument
    2. SYS2TXT_WHISPER_CPP_MODELS directory + ggml-{model_size}.bin
    3. ~/.local/share/whisper.cpp/models/ggml-{model_size}.bin

    Args:
        model_path: Explicit path to model file
        model_size: Whisper model size (tiny, base, small, medium, large-v2)

    Returns:
        Path to model file

    Raises:
        RuntimeError: If model file cannot be found
    """
    if model_path:
        if not os.path.isfile(model_path):
            raise RuntimeError(f"whisper.cpp model not found at: {model_path}")
        return model_path

    model_filename = f"ggml-{model_size}.bin"

    env_models_dir = os.environ.get("SYS2TXT_WHISPER_CPP_MODELS")
    if env_models_dir:
        env_model_path = os.path.join(env_models_dir, model_filename)
        if os.path.isfile(env_model_path):
            return env_model_path

    default_dir = Path.home() / ".local" / "share" / "whisper.cpp" / "models"
    default_path = default_dir / model_filename
    if default_path.is_file():
        return str(default_path)

    raise RuntimeError(
        f"whisper.cpp model '{model_filename}' not found. Either:\n"
        "  1. Use --model-path to specify the model file\n"
        f"  2. Set SYS2TXT_WHISPER_CPP_MODELS to directory containing {model_filename}\n"
        f"  3. Place model at {default_path}"
    )


def _parse_whisper_cpp_output(output: str, timestamps: bool) -> str:
    """Parse whisper.cpp stdout format.

    Whisper.cpp outputs lines like:
    [00:00:00.000 --> 00:00:05.120]   Hello world

    Args:
        output: Raw stdout from whisper-cli
        timestamps: Whether to include timestamps in output

    Returns:
        Parsed transcription text
    """
    lines = []
    # Pattern: [HH:MM:SS.mmm --> HH:MM:SS.mmm] text
    pattern = re.compile(r"\[(\d{2}:\d{2}:\d{2}\.\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}\.\d{3})\]\s*(.*)")

    for line in output.splitlines():
        match = pattern.match(line.strip())
        if match:
            start_str, end_str, text = match.groups()
            text = text.strip()
            if not text:
                continue
            if timestamps:
                # Convert HH:MM:SS.mmm to seconds for consistent formatting
                start_secs = _timestamp_to_seconds(start_str)
                end_secs = _timestamp_to_seconds(end_str)
                lines.append(f"[{start_secs:6.2f}-{end_secs:6.2f}] {text}")
            else:
                lines.append(text)

    if timestamps:
        return "\n".join(lines)
    else:
        return " ".join(lines).strip()


def _timestamp_to_seconds(ts: str) -> float:
    """Convert HH:MM:SS.mmm timestamp to seconds.

    Args:
        ts: Timestamp string like "00:01:23.456"

    Returns:
        Time in seconds as float
    """
    try:
        parts = ts.split(":")
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
        return hours * 3600 + minutes * 60 + seconds
    except (IndexError, ValueError):
        return 0.0


def _transcribe_whisper_cpp(
    path: str,
    model_size: str,
    language: Optional[str],
    timestamps: bool,
    model_path: Optional[str],
    whisper_cpp_path: Optional[str],
    device: str,
) -> str:
    """Transcribe using whisper.cpp (with optional Vulkan GPU support).

    Args:
        path: Path to audio file
        model_size: Whisper model size (tiny, base, small, medium, large-v2)
        language: Optional language code (e.g., "en"). If None, auto-detect.
        timestamps: Whether to include timestamps in output
        model_path: Path to whisper.cpp model file
        whisper_cpp_path: Path to whisper-cli binary
        device: Device to use ("auto", "cpu", "vulkan", "gpu", "cuda")

    Returns:
        Transcribed text

    Raises:
        RuntimeError: If whisper-cli binary or model not found, or transcription fails
    """
    binary = _resolve_whisper_cpp_binary(whisper_cpp_path)
    model = _resolve_whisper_cpp_model_path(model_path, model_size)

    # Build command
    cmd = [binary, "-m", model, "-f", path, "-np"]  # -np = no progress

    # Device selection
    if device == "cpu":
        cmd.append("--no-gpu")
    # For auto/vulkan/gpu/cuda, let whisper.cpp use GPU if available

    if language:
        cmd.extend(["-l", language])

    if not timestamps:
        cmd.append("--no-timestamps")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=300)
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(
            f"whisper-cli timed out after 300 seconds (possible GPU hang or malformed audio): {binary}"
        ) from e
    except subprocess.CalledProcessError as e:
        stderr = e.stderr.strip() if e.stderr else "No error output"
        raise RuntimeError(f"whisper-cli failed: {stderr}") from e
    except FileNotFoundError as e:
        raise RuntimeError(f"whisper-cli binary not found: {binary}") from e

    return _parse_whisper_cpp_output(result.stdout, timestamps)
