"""Transcription entry points.

Turning an audio file into a transcript is two decisions: which engine, and what the
result should look like. This module makes the first by asking
:func:`sys2txt.engines.get_engine`, and leaves the second to :mod:`sys2txt.formats`.
The engines themselves live in :mod:`sys2txt.engines`.
"""

import logging

from .engines import TranscriptionConfig, get_engine
from .formats import Transcript, render_transcript

logger = logging.getLogger(__name__)

__all__ = ["TranscriptionConfig", "transcribe_file", "transcribe_file_cues"]


def transcribe_file(path: str, config: TranscriptionConfig) -> str:
    """Transcribe an audio file and return its text.

    Args:
        path: Path to audio file
        config: Transcription configuration

    Returns:
        Transcribed text, one line per cue when ``config.timestamps`` is set

    Raises:
        ValueError: If the configured engine is unknown
        RuntimeError: If ``config.engine`` is ``"auto"`` and no engine is installed
    """
    transcript = transcribe_file_cues(path, config)
    return render_transcript(transcript.cues, "txt", timestamps=config.timestamps)


def transcribe_file_cues(path: str, config: TranscriptionConfig) -> Transcript:
    """Transcribe an audio file into timed cues.

    This is the structured form of :func:`transcribe_file`, keeping the per-utterance
    timings that the subtitle and JSON output formats need.

    Args:
        path: Path to audio file
        config: Transcription configuration

    Returns:
        The transcript, with cue times in seconds from the start of the audio file

    Raises:
        ValueError: If the configured engine is unknown
        RuntimeError: If ``config.engine`` is ``"auto"`` and no engine is installed
    """
    engine = get_engine(config.engine.lower())
    logger.debug("Transcribing %s with engine '%s', model '%s'", path, engine.name, config.model)
    return engine.transcribe(path, config)
