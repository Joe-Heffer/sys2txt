"""Audio recording functionality using ffmpeg and PulseAudio/PipeWire."""

import logging
import os
import signal
import subprocess
import tempfile
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
        path: Path to the segment's WAV file. It lives in a temporary directory that is
            removed once the producing generator is closed, so copy it if you need it later.
    """

    index: int
    path: str


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

    proc = subprocess.Popen(args)
    try:
        proc.wait()
    except KeyboardInterrupt:
        try:
            proc.send_signal(signal.SIGINT)
        except OSError:
            pass
        proc.wait()
    logger.info("Recording finished.")


def _segment_files(directory: str) -> List[str]:
    """Return the segment filenames in chronological order."""
    return sorted(f for f in os.listdir(directory) if f.startswith("seg_") and f.endswith(".wav"))


def iter_audio_segments(
    source: str,
    segment_seconds: int = DEFAULT_SEGMENT_SECONDS,
    *,
    sample_rate: int = SAMPLE_RATE,
    channels: int = CHANNELS,
) -> Iterator[AudioSegment]:
    """Record continuously and yield each segment of audio as ffmpeg finalizes it.

    Recording runs until the consumer stops iterating: breaking out of the loop, closing the
    generator, or letting it be garbage collected shuts ffmpeg down gracefully and removes the
    temporary directory holding the segments.

    Args:
        source: PulseAudio source name
        segment_seconds: Length of each segment in seconds
        sample_rate: Sample rate in Hz
        channels: Number of audio channels

    Yields:
        AudioSegment values in chronological order. Segment files that hold no audio are
        skipped, but their index is still consumed so an index always maps to the same
        position on the recording's timeline.
    """
    ffmpeg = which("ffmpeg")
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
        seen: set[str] = set()
        next_index = 0

        def emit(names):
            """Yield an AudioSegment for each name not seen before."""
            nonlocal next_index
            for name in names:
                if name in seen:
                    continue
                seen.add(name)
                index = next_index
                next_index += 1
                path = os.path.join(tmp, name)
                if os.path.getsize(path) < MIN_SEGMENT_BYTES:
                    logger.debug("Segment %s holds no audio, skipping", name)
                    continue
                yield AudioSegment(index=index, path=path)

        try:
            while True:
                files = _segment_files(tmp)
                # While ffmpeg is running, the last file is always the one currently
                # being written. Only process files that have been finalized, which is
                # guaranteed when a newer segment exists after them.
                yield from emit(files[:-1] if len(files) > 1 else [])

                if proc.poll() is not None:
                    # ffmpeg has exited, so every remaining file is finalized
                    yield from emit(_segment_files(tmp))
                    break
                time.sleep(SEGMENT_POLL_INTERVAL)
        finally:
            _stop_ffmpeg(proc)
            logger.info("Stopped live capture.")
