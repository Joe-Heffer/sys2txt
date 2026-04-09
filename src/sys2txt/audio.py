"""Audio recording functionality using ffmpeg and PulseAudio/PipeWire."""

import logging
import os
import signal
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Optional

from .utils import which

logger = logging.getLogger(__name__)


class _SilenceTimeout(Exception):
    """Raised internally when consecutive silence exceeds the timeout."""


def _stop_ffmpeg(proc, executor):
    """Gracefully stop ffmpeg and shut down the transcription executor."""
    executor.shutdown(wait=False)
    try:
        if proc.stdin:
            proc.stdin.write(b"q")
            proc.stdin.flush()
            proc.stdin.close()
        try:
            proc.wait(timeout=3.0)
        except subprocess.TimeoutExpired:
            proc.terminate()
            proc.wait()
    except OSError:
        pass


def record_once(source: str, out_wav: str, sample_rate: int, channels: int, duration: Optional[int]) -> None:
    """Record audio once from a PulseAudio source to a WAV file.

    Args:
        source: PulseAudio source name (e.g., "sink.monitor")
        out_wav: Output WAV file path
        sample_rate: Sample rate in Hz (e.g., 16000)
        channels: Number of audio channels (1 for mono, 2 for stereo)
        duration: Optional recording duration in seconds. If None, records until interrupted.
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


def _process_segment_file(f, tmp, processed, transcribe_callback, output_path, executor, timeout):
    """Process a single finalized segment file: transcribe and print/write output."""
    full = os.path.join(tmp, f)
    if os.path.getsize(full) < 64:
        return ""
    processed.add(f)
    try:
        idx = int(os.path.splitext(f)[0].split("_")[-1])
    except (ValueError, IndexError):
        idx = 0
    if executor and timeout:
        future = executor.submit(transcribe_callback, full, idx)
        try:
            text = future.result(timeout=timeout)
        except FuturesTimeoutError:
            logger.warning("Segment %s transcription timed out, skipping", f)
            return ""
        except Exception as e:
            logger.warning("Segment %s transcription failed: %s", f, e)
            return ""
    else:
        text = transcribe_callback(full, idx)
    print(text, flush=True)
    if output_path:
        with open(output_path, "a", encoding="utf-8") as w:
            w.write(text + "\n")
    return text


def segment_and_transcribe_live(
    source: str,
    sample_rate: int,
    channels: int,
    segment_seconds: int,
    transcribe_callback,
    output_path: Optional[str],
    silence_timeout: int = 0,
) -> None:
    """Record audio in segments and transcribe each segment as it's created.

    Args:
        source: PulseAudio source name
        sample_rate: Sample rate in Hz
        channels: Number of audio channels
        segment_seconds: Length of each segment in seconds
        transcribe_callback: Function to call for each segment. Should accept (file_path, segment_index) and return text
        output_path: Optional file path to append transcripts to
        silence_timeout: Auto-stop after this many consecutive seconds of silence (0 = disabled)
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

        logger.info("Live mode: segmenting every %ds from '%s'. Press Ctrl-C to stop.", segment_seconds, source)
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        processed: set[str] = set()
        # Timeout: allow generous time but prevent indefinite hangs
        transcribe_timeout = max(segment_seconds * 5, 60)
        executor = ThreadPoolExecutor(max_workers=1)
        consecutive_silent_seconds = 0
        try:
            while True:
                # sorted ensures we process in chronological order
                files = sorted(f for f in os.listdir(tmp) if f.startswith("seg_") and f.endswith(".wav"))
                # While ffmpeg is running, the last file is always the one currently
                # being written. Only process files that have been finalized, which is
                # guaranteed when a newer segment exists after them.
                safe_to_process = files[:-1] if len(files) > 1 else []
                new_files = [f for f in safe_to_process if f not in processed]
                for f in new_files:
                    text = _process_segment_file(
                        f, tmp, processed, transcribe_callback, output_path, executor, transcribe_timeout
                    )
                    if silence_timeout > 0:
                        if not text or not text.strip():
                            consecutive_silent_seconds += segment_seconds
                        else:
                            consecutive_silent_seconds = 0
                        if consecutive_silent_seconds >= silence_timeout:
                            raise _SilenceTimeout()

                # If ffmpeg has exited and no new files pending, break
                ret = proc.poll()
                if ret is not None:
                    # flush remaining unprocessed files (including the last segment)
                    files = sorted(f for f in os.listdir(tmp) if f.startswith("seg_") and f.endswith(".wav"))
                    for f in [f for f in files if f not in processed]:
                        _process_segment_file(
                            f, tmp, processed, transcribe_callback, output_path, executor, transcribe_timeout
                        )
                    break
                time.sleep(0.3)
        except KeyboardInterrupt:
            logger.info("Stopping live capture...")
            _stop_ffmpeg(proc, executor)
            logger.info("Stopped live capture.")
        except _SilenceTimeout:
            logger.info(
                "No speech detected for %d seconds, stopping automatically.",
                consecutive_silent_seconds,
            )
            _stop_ffmpeg(proc, executor)
