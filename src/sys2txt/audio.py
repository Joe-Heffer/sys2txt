"""Audio recording functionality using ffmpeg and PulseAudio/PipeWire."""

import contextlib
import logging
import os
import signal
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from typing import Iterator, List, Optional

from .constants import (
    CHANNELS,
    DEFAULT_SEGMENT_SECONDS,
    FFMPEG_SHUTDOWN_GRACE,
    MIN_SEGMENT_BYTES,
    SAMPLE_RATE,
    SEGMENT_POLL_INTERVAL,
)
from .utils import which

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AudioSegment:
    """A finalized chunk of recorded audio.

    Attributes:
        index: Position of the segment in the recording, counting from 0
        path: Path to the segment's WAV file. It is removed as soon as the consumer asks for
            the next segment, so copy it if you need it later.
        lag: Seconds of finalized audio recorded but not yet handed out, queued behind this
            segment. Zero while transcription keeps up with recording.
        dropped: Segments discarded immediately before this one to catch up, so a consumer can
            see the hole. Always 0 unless ``max_lag`` is set.
    """

    index: int
    path: str
    lag: float = 0.0
    dropped: int = 0


def _drain_stderr(proc: subprocess.Popen, lines: Optional[List[str]] = None) -> None:
    """Read ffmpeg's stderr to completion, logging each line.

    ffmpeg's stderr is a pipe with a finite OS buffer; if nothing reads it, ffmpeg blocks on
    write once that buffer fills and the process wedges without exiting. This runs in its own
    thread so the pipe is always drained, and stops when it hits EOF (ffmpeg has exited).

    ``lines``, if given, additionally collects each line so a caller can report ffmpeg's own
    diagnostic on failure rather than just discarding it into the log.
    """
    if proc.stderr is None:
        return
    for line in proc.stderr:
        text = line.decode("utf-8", errors="replace").rstrip()
        if text:
            logger.warning("ffmpeg: %s", text)
            if lines is not None:
                lines.append(text)


def _stop_ffmpeg(proc: subprocess.Popen) -> None:
    """Ask ffmpeg to quit, then terminate it if it does not exit in time."""
    try:
        if proc.poll() is not None:
            return
        if proc.stdin:
            proc.stdin.write(b"q")
            proc.stdin.flush()
            proc.stdin.close()
        try:
            proc.wait(timeout=FFMPEG_SHUTDOWN_GRACE)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait()
    except OSError:
        pass


def record_once(
    source: str,
    out_wav: str,
    duration: Optional[int] = None,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
) -> None:
    """Record audio once from a PulseAudio source to a WAV file.

    Args:
        source: PulseAudio source name (e.g., "sink.monitor")
        out_wav: Output WAV file path
        duration: Optional recording duration in seconds. If None, records until interrupted.
        sample_rate: Sample rate in Hz
        channels: Number of audio channels (1 for mono, 2 for stereo)

    Raises:
        RuntimeError: ffmpeg exited with a non-zero status for a reason other than the
            interrupt this function sent it to stop recording, naming ffmpeg's own diagnostic.
    """
    ffmpeg = which("ffmpeg")
    args = [
        ffmpeg,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "pulse",
        "-i",
        source,
        "-ac",
        str(channels),
        "-ar",
        str(sample_rate),
        "-f",
        "wav",
    ]
    if duration is not None and duration > 0:
        args.extend(["-t", str(duration)])
    args.append(out_wav)

    logger.info("Recording system audio from source '%s' at %d Hz, mono -> %s", source, sample_rate, out_wav)
    if duration is None:
        logger.info("Press Ctrl-C to stop early...")
    else:
        logger.info("Recording for %d seconds...", duration)

    stderr_lines: List[str] = []
    proc = subprocess.Popen(args, stderr=subprocess.PIPE)
    stderr_thread = threading.Thread(target=_drain_stderr, args=(proc, stderr_lines), daemon=True)
    stderr_thread.start()
    interrupted = False
    try:
        proc.wait()
    except KeyboardInterrupt:
        interrupted = True
        try:
            proc.send_signal(signal.SIGINT)
        except OSError:
            pass
        proc.wait()
    stderr_thread.join()

    if not interrupted and proc.returncode != 0:
        detail = "\n".join(stderr_lines) or f"ffmpeg exited with code {proc.returncode}"
        raise RuntimeError(f"ffmpeg failed while recording: {detail}")

    logger.info("Recording finished.")


def _segment_files(directory: str) -> List[str]:
    """Return the segment filenames in chronological order."""
    return sorted(f for f in os.listdir(directory) if f.startswith("seg_") and f.endswith(".wav"))


def _discard(path: str) -> None:
    """Remove a segment file we are done with, ignoring one that has already gone."""
    with contextlib.suppress(OSError):
        os.remove(path)


def iter_audio_segments(
    source: str,
    segment_seconds: int = DEFAULT_SEGMENT_SECONDS,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
    max_lag: float = 0.0,
) -> Iterator[AudioSegment]:
    """Record continuously and yield each segment of audio as ffmpeg finalizes it.

    Recording runs until the consumer stops iterating: breaking out of the loop, closing the
    generator, or letting it be garbage collected shuts ffmpeg down gracefully and removes the
    temporary directory holding the segments.

    ffmpeg finalizes a segment every ``segment_seconds`` whatever the consumer is doing, so a
    consumer slower than realtime falls behind. Each segment reports how much audio is queued
    behind it as its ``lag``; ``max_lag`` caps that queue by discarding the oldest segments,
    trading audio for staying close to live.

    Args:
        source: PulseAudio source name
        segment_seconds: Length of each segment in seconds
        sample_rate: Sample rate in Hz
        channels: Number of audio channels
        max_lag: Seconds of queued audio to tolerate before dropping the oldest segments,
            or 0 to keep everything however far behind the consumer falls

    Yields:
        AudioSegment values in chronological order. Segment files that hold no audio are
        skipped, and dropped ones are never yielded, but their indices are still consumed so an
        index always maps to the same position on the recording's timeline.
    """
    ffmpeg = which("ffmpeg")
    # Keeping fewer than one segment would drop every segment as soon as it was finalized
    keep = max(1, int(max_lag // segment_seconds)) if max_lag > 0 else 0
    with tempfile.TemporaryDirectory(prefix="sys2txt_") as tmp:
        pattern = os.path.join(tmp, "seg_%05d.wav")
        args = [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "pulse",
            "-i",
            source,
            "-ac",
            str(channels),
            "-ar",
            str(sample_rate),
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-reset_timestamps",
            "1",
            pattern,
        ]

        logger.info("Live mode: segmenting every %ds from '%s'.", segment_seconds, source)
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        threading.Thread(target=_drain_stderr, args=(proc,), daemon=True).start()
        seen: set[str] = set()
        queue: List[str] = []
        next_index = 0
        dropped = 0

        try:
            # One segment is handed out per pass, so the queue is re-measured, and the drop
            # policy re-applied, every time the consumer comes back for more.
            while True:
                # Poll before listing, so a listing taken after ffmpeg exited is complete
                finished = proc.poll() is not None
                files = _segment_files(tmp)
                # While ffmpeg is running, the last file is always the one currently being
                # written. Only process files that have been finalized, which is guaranteed
                # when a newer segment exists after them.
                for name in files if finished else files[:-1]:
                    if name not in seen:
                        seen.add(name)
                        queue.append(name)

                if keep and len(queue) > keep:
                    stale, queue = queue[:-keep], queue[-keep:]
                    for name in stale:
                        next_index += 1
                        dropped += 1
                        _discard(os.path.join(tmp, name))
                    logger.warning(
                        "Transcription is behind: dropped %d segment(s), %ds of audio, to catch up",
                        len(stale),
                        len(stale) * segment_seconds,
                    )

                if queue:
                    name = queue.pop(0)
                    index = next_index
                    next_index += 1
                    path = os.path.join(tmp, name)
                    if os.path.getsize(path) < MIN_SEGMENT_BYTES:
                        logger.debug("Segment %s holds no audio, skipping", name)
                        _discard(path)
                        continue
                    yield AudioSegment(
                        index=index,
                        path=path,
                        lag=len(queue) * float(segment_seconds),
                        dropped=dropped,
                    )
                    dropped = 0
                    # The consumer has moved on, so the temporary directory holds the backlog
                    # rather than every segment of the session.
                    _discard(path)
                    continue

                if finished:
                    break
                time.sleep(SEGMENT_POLL_INTERVAL)
        finally:
            _stop_ffmpeg(proc)
            logger.info("Stopped live capture.")
