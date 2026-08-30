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
    LAG_WARN_FACTOR,
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
        text: Transcribed text, empty when the segment held no speech or when ``error`` is set
        start: Start of the segment in seconds from the beginning of the recording
        end: End of the segment in seconds from the beginning of the recording
        cues: The engine's own timed spans of speech within the segment, rebased onto the
            recording timeline so their times are comparable with ``start`` and ``end``.
            Empty when the segment held no speech or transcription failed.
        error: Why transcription failed, or None when it succeeded. Silence and failure both
            leave ``text`` empty, so this is what tells them apart.
        lag: Seconds of recorded audio waiting to be transcribed behind this segment. Zero
            while transcription keeps up with recording.
        dropped: Segments discarded immediately before this one to catch up, leaving a hole in
            the transcript. Always 0 unless ``max_lag`` is set.
    """

    index: int
    text: str
    start: float
    end: float
    cues: Tuple[Cue, ...] = ()
    error: Optional[str] = None
    lag: float = 0.0
    dropped: int = 0

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


def _warn_lag(lag: float, segment_seconds: int, warned_at: float) -> float:
    """Warn that transcription is falling behind, and return the lag last warned about.

    Recording carries on at its own pace, so a consumer slower than realtime falls further
    behind every segment. Warn once the backlog is worth noticing, then only as it grows by
    another segment, so a slow run reports its drift without filling the log.
    """
    if lag <= LAG_WARN_FACTOR * segment_seconds:
        return 0.0
    if lag < warned_at + segment_seconds:
        return warned_at
    logger.warning(
        "Transcription is not keeping up: %.0fs of audio (%d segments) waiting to be transcribed",
        lag,
        round(lag / segment_seconds),
    )
    return lag


def transcribe_live(
    source: str,
    config: TranscriptionConfig,
    *,
    segment_seconds: int = DEFAULT_SEGMENT_SECONDS,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
    max_lag: float = 0.0,
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
        max_lag: Seconds of untranscribed audio to tolerate before dropping the oldest
            segments, or 0 to keep everything however far behind transcription falls

    Yields:
        TranscriptSegment values in chronological order. A segment whose transcription times
        out or fails is yielded with empty text, an ``error`` describing the failure, and a
        warning in the log. Each segment reports how far transcription is behind as its
        ``lag``, which is warned about in the log as it grows.
    """
    timeout = _segment_timeout(segment_seconds)
    segments = iter_audio_segments(source, segment_seconds, sample_rate=sample_rate, channels=channels, max_lag=max_lag)
    executor = _new_executor()
    warned_at = 0.0
    future = None
    try:
        for segment in segments:
            warned_at = _warn_lag(segment.lag, segment_seconds, warned_at)
            future = executor.submit(transcribe_file_cues, segment.path, config)
            error = None
            try:
                transcript = future.result(timeout=timeout)
                future = None
            except FuturesTimeoutError:
                logger.warning("Segment %d transcription timed out, skipping", segment.index)
                transcript = Transcript()
                error = f"transcription timed out after {timeout:.0f}s"
                # The worker cannot be cancelled and keeps running, so the next segment
                # would queue behind it and time out without ever being transcribed.
                # Abandon the pool and give the next segment a worker of its own.
                executor.shutdown(wait=False)
                executor = _new_executor()
                future = None
            except Exception as e:
                logger.warning("Segment %d transcription failed: %s", segment.index, e)
                transcript = Transcript()
                error = f"transcription failed: {e}"
                future = None
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
                error=error,
                lag=segment.lag,
                dropped=segment.dropped,
            )
    finally:
        # A worker can still be transcribing here if we were interrupted (e.g. Ctrl-C)
        # while future.result() was blocked above. Give it a bounded chance to finish
        # before closing the segment generator, whose cleanup removes the temporary
        # directory the worker is reading from.
        if future is not None and not future.done():
            with contextlib.suppress(FuturesTimeoutError):
                future.result(timeout=timeout)
        executor.shutdown(wait=False)
        segments.close()


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
