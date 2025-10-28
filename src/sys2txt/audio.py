"""Audio recording functionality using ffmpeg and PulseAudio/PipeWire."""

import os
import signal
import subprocess
import tempfile
import time
from typing import Optional

from .utils import which


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

    print(f"Recording system audio from source '{source}' at {sample_rate} Hz, mono -> {out_wav}")
    print("Press Ctrl-C to stop early..." if duration is None else f"Recording for {duration} seconds...")

    proc = subprocess.Popen(args)
    try:
        proc.wait()
    except KeyboardInterrupt:
        try:
            proc.send_signal(signal.SIGINT)
        except Exception:
            pass
        proc.wait()
    print("Recording finished.")


def segment_and_transcribe_live(
    source: str,
    sample_rate: int,
    channels: int,
    segment_seconds: int,
    transcribe_callback,
    output_path: Optional[str],
) -> None:
    """Record audio in segments and transcribe each segment as it's created.

    Args:
        source: PulseAudio source name
        sample_rate: Sample rate in Hz
        channels: Number of audio channels
        segment_seconds: Length of each segment in seconds
        transcribe_callback: Function to call for each segment. Should accept (file_path, segment_index) and return text.
        output_path: Optional file path to append transcripts to
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

        print(f"Live mode: segmenting every {segment_seconds}s from '{source}'. Press Ctrl-C to stop.")
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        processed: set[str] = set()
        try:
            while True:
                # sorted ensures we process in chronological order
                files = sorted(f for f in os.listdir(tmp) if f.startswith("seg_") and f.endswith(".wav"))
                new_files = [f for f in files if f not in processed]
                for f in new_files:
                    full = os.path.join(tmp, f)
                    # Ensure the segment has been finalized and has content
                    if os.path.getsize(full) < 64:
                        continue
                    processed.add(f)

                    # Extract segment index from filename
                    try:
                        idx = int(os.path.splitext(f)[0].split("_")[-1])
                    except Exception:
                        idx = 0

                    text = transcribe_callback(full, idx)
                    print(text, flush=True)
                    if output_path:
                        with open(output_path, "a", encoding="utf-8") as w:
                            w.write(text + "\n")

                # If ffmpeg has exited and no new files pending, break
                ret = proc.poll()
                if ret is not None:
                    # flush remaining unprocessed files
                    files = sorted(f for f in os.listdir(tmp) if f.startswith("seg_") and f.endswith(".wav"))
                    new_files = [f for f in files if f not in processed]
                    for f in new_files:
                        full = os.path.join(tmp, f)
                        if os.path.getsize(full) < 64:
                            continue
                        processed.add(f)
                        try:
                            idx = int(os.path.splitext(f)[0].split("_")[-1])
                        except Exception:
                            idx = 0
                        text = transcribe_callback(full, idx)
                        print(text, flush=True)
                        if output_path:
                            with open(output_path, "a", encoding="utf-8") as w:
                                w.write(text + "\n")
                    break
                time.sleep(0.3)
        except KeyboardInterrupt:
            print("\nStopping live capture...")
            try:
                # Send 'q' command to ffmpeg to quit gracefully
                if proc.stdin:
                    proc.stdin.write(b"q")
                    proc.stdin.flush()
                    proc.stdin.close()
                # Give ffmpeg time to finish the current segment
                try:
                    proc.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    # If it doesn't finish in time, terminate it
                    proc.terminate()
                    proc.wait()
            except Exception:
                pass
            print("Stopped live capture.")
