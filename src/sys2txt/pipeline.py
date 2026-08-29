"""Recording and transcription combined into reusable pipelines."""

import contextlib
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Iterator, Optional, Tuple

from .audio import iter_audio_segments, record_once
from .constants import (
    CHANNELS,
    DEFAULT_SEGMENT_SECONDS,
    MIN_TRANSCRIBE_TIMEOUT,
    SAMPLE_RATE,
    TRANSCRIBE_TIMEOUT_FACTOR,
)
from .formats import Cue, Transcript, render_transcript
from .transcribe import TranscriptionConfig, transcribe_file_cues

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptSegment:
    """The transcript of one segment of a live recording.

    Attributes:
        index: Position of the segment in the recording, counting from 0
        text: Transcribed text, empty when the segment held no speech or transcription failed
        start: Start of the segment in seconds from the beginning of the recording
        end: End of the segment in seconds from the beginning of the recording
        cues: The engine's own timed spans of speech within the segment, rebased onto the
            recording timeline so their times are comparable with ``start`` and ``end``.
            Empty when the segment held no speech or transcription failed.
    """

    index: int
    text: str
    start: float
    end: float
    cues: Tuple[Cue, ...] = ()


def _segment_timeout(segment_seconds: int) -> float:
    """Allow generous time to transcribe a segment while preventing indefinite hangs."""
    return max(segment_seconds * TRANSCRIBE_TIMEOUT_FACTOR, MIN_TRANSCRIBE_TIMEOUT)


def transcribe_live(
    source: str,
    config: TranscriptionConfig,
    *,
    segment_seconds: int = DEFAULT_SEGMENT_SECONDS,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
) -> Iterator[TranscriptSegment]:
    """Record continuously and yield the transcript of each segment as it becomes available.

    Recording runs until the consumer stops iterating, so a caller decides when to stop by
    breaking out of the loop or closing the generator. Transcription of a segment blocks the
    generator, but ffmpeg keeps recording in the background while it runs.

    Args:
        source: PulseAudio source name
        config: Transcription configuration
        segment_seconds: Length of each segment in seconds
        sample_rate: Sample rate in Hz
        channels: Number of audio channels

    Yields:
        TranscriptSegment values in chronological order. A segment whose transcription times
        out or fails is yielded with empty text and logged as a warning.
    """
    timeout = _segment_timeout(segment_seconds)
    segments = iter_audio_segments(source, segment_seconds, sample_rate=sample_rate, channels=channels)
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        with contextlib.closing(segments):
            for segment in segments:
                future = executor.submit(transcribe_file_cues, segment.path, config)
                try:
                    transcript = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    logger.warning("Segment %d transcription timed out, skipping", segment.index)
                    transcript = Transcript()
                except Exception as e:
                    logger.warning("Segment %d transcription failed: %s", segment.index, e)
                    transcript = Transcript()
                start = segment.index * segment_seconds
                # The engine times each segment from zero, so shift its cues onto the
                # timeline of the recording as a whole.
                cues = tuple(cue.shifted(float(start)) for cue in transcript.cues)
                yield TranscriptSegment(
                    index=segment.index,
                    text=render_transcript(transcript.cues, "txt", timestamps=config.timestamps),
                    start=float(start),
                    end=float(start + segment_seconds),
                    cues=cues,
                )
    finally:
        executor.shutdown(wait=False)


def transcribe_once(
    source: str,
    config: TranscriptionConfig,
    duration: Optional[int] = None,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
) -> str:
    """Record audio once and return its transcript as text.

    Args:
        source: PulseAudio source name
        config: Transcription configuration
        duration: Recording duration in seconds. If None, records until interrupted.
        sample_rate: Sample rate in Hz
        channels: Number of audio channels

    Returns:
        Transcribed text
    """
    transcript = transcribe_once_cues(source, config, duration, sample_rate=sample_rate, channels=channels)
    return render_transcript(transcript.cues, "txt", timestamps=config.timestamps)


def transcribe_once_cues(
    source: str,
    config: TranscriptionConfig,
    duration: Optional[int] = None,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
) -> Transcript:
    """Record audio once and return its transcript as timed cues.

    This is the structured form of :func:`transcribe_once`, keeping the per-utterance
    timings that the subtitle and JSON output formats need.

    Args:
        source: PulseAudio source name
        config: Transcription configuration
        duration: Recording duration in seconds. If None, records until interrupted.
        sample_rate: Sample rate in Hz
        channels: Number of audio channels

    Returns:
        The transcript, with cue times in seconds from the start of the recording
    """
    with tempfile.TemporaryDirectory(prefix="sys2txt_") as tmp:
        wav = os.path.join(tmp, "capture.wav")
        record_once(source, wav, duration, sample_rate=sample_rate, channels=channels)
        return transcribe_file_cues(wav, config)
