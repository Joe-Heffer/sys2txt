"""Transcription functionality using Whisper models."""

import os
from typing import Optional


def transcribe_file(path: str, engine: str, model_size: str, language: Optional[str], timestamps: bool) -> str:
    """Transcribe an audio file using the specified Whisper engine.

    Args:
        path: Path to audio file
        engine: Engine to use ("auto", "faster", or "whisper")
        model_size: Whisper model size (tiny, base, small, medium, large-v2)
        language: Optional language code (e.g., "en"). If None, auto-detect.
        timestamps: Whether to include timestamps in output

    Returns:
        Transcribed text
    """
    engine = engine.lower()
    if engine == "auto":
        try:
            import faster_whisper  # type: ignore

            engine = "faster"
        except Exception:
            engine = "whisper"

    if engine == "faster":
        return _transcribe_faster_whisper(path, model_size, language, timestamps)
    elif engine == "whisper":
        return _transcribe_openai_whisper(path, model_size, language, timestamps)
    else:
        raise ValueError(f"Unknown engine: {engine}")


def _transcribe_faster_whisper(path: str, model_size: str, language: Optional[str], timestamps: bool) -> str:
    """Transcribe using faster-whisper (ctranslate2 backend)."""
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as e:
        raise RuntimeError("faster-whisper is not installed. pip install faster-whisper") from e

    # Auto device selection
    device = "cpu"
    compute_type = "int8"
    # If user has a CUDA-enabled ctranslate2 build installed, they can switch manually by editing below
    # or by setting environment variable SYS2TXT_DEVICE=cuda
    if os.environ.get("SYS2TXT_DEVICE") == "cuda":
        device = "cuda"
        compute_type = "float16"

    model = WhisperModel(model_size, device=device, compute_type=compute_type)
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
    except Exception as e:
        raise RuntimeError("openai-whisper is not installed. pip install openai-whisper") from e

    model = whisper.load_model(model_size)
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
