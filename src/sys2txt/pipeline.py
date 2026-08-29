"""Recording and transcription combined into reusable pipelines."""

import contextlib
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from dataclasses import dataclass
from typing import Iterator, Optional

from .audio import iter_audio_segments, record_once
from .constants import (
    CHANNELS,
    DEFAULT_SEGMENT_SECONDS,
    MIN_TRANSCRIBE_TIMEOUT,
    SAMPLE_RATE,
    TRANSCRIBE_TIMEOUT_FACTOR,
)
from .transcribe import TranscriptionConfig, transcribe_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscriptSegment:
    """The transcript of one segment of a live recording.

    Attributes:
        index: Position of the segment in the recording, counting from 0
        text: Transcribed text, empty when the segment held no speech or when ``error`` is set
        start: Start of the segment in seconds from the beginning of the recording
        end: End of the segment in seconds from the beginning of the recording
        error: Why transcription failed, or None when it succeeded. Silence and failure both
            leave ``text`` empty, so this is what tells them apart.
    """

    index: int
    text: str
    start: float
    end: float
    error: Optional[str] = None

    @property
    def failed(self) -> bool:
        """Whether transcription of this segment failed rather than finding no speech."""
        return self.error is not None


def _segment_timeout(segment_seconds: int) -> float:
    """Allow generous time to transcribe a segment while preventing indefinite hangs."""
    return max(segment_seconds * TRANSCRIBE_TIMEOUT_FACTOR, MIN_TRANSCRIBE_TIMEOUT)


def _new_executor() -> ThreadPoolExecutor:
    """Create the single-worker pool that transcribes one segment at a time."""
    return ThreadPoolExecutor(max_workers=1)


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
        out or fails is yielded with empty text, an ``error`` describing the failure, and a
        warning in the log.
    """
    timeout = _segment_timeout(segment_seconds)
    segments = iter_audio_segments(source, segment_seconds, sample_rate=sample_rate, channels=channels)
    executor = _new_executor()
    try:
        with contextlib.closing(segments):
            for segment in segments:
                future = executor.submit(transcribe_file, segment.path, config)
                error = None
                text = ""
                try:
                    text = future.result(timeout=timeout)
                except FuturesTimeoutError:
                    logger.warning("Segment %d transcription timed out, skipping", segment.index)
                    error = f"transcription timed out after {timeout:.0f}s"
                    # The worker cannot be cancelled and keeps running, so the next segment
                    # would queue behind it and time out without ever being transcribed.
                    # Abandon the pool and give the next segment a worker of its own.
                    executor.shutdown(wait=False)
                    executor = _new_executor()
                except Exception as e:
                    logger.warning("Segment %d transcription failed: %s", segment.index, e)
                    error = f"transcription failed: {e}"
                start = segment.index * segment_seconds
                yield TranscriptSegment(
                    index=segment.index,
                    text=text,
                    start=float(start),
                    end=float(start + segment_seconds),
                    error=error,
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
    """Record audio once and return its transcript.

    Args:
        source: PulseAudio source name
        config: Transcription configuration
        duration: Recording duration in seconds. If None, records until interrupted.
        sample_rate: Sample rate in Hz
        channels: Number of audio channels

    Returns:
        Transcribed text
    """
    with tempfile.TemporaryDirectory(prefix="sys2txt_") as tmp:
        wav = os.path.join(tmp, "capture.wav")
        record_once(source, wav, duration, sample_rate=sample_rate, channels=channels)
        return transcribe_file(wav, config)
