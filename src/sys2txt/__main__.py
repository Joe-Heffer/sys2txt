#!/usr/bin/env python3
import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from typing import List, Optional, Tuple


def which(cmd: str) -> str:
    path = shutil.which(cmd)
    if not path:
        raise RuntimeError(f"Required command not found: {cmd}. Please install it and try again.")
    return path


def run(cmd: List[str]) -> Tuple[int, str, str]:
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return p.returncode, out, err


def list_pulse_sources() -> List[Tuple[str, str]]:
    """Return list of (name, description) for PulseAudio sources."""
    try:
        code, out, _ = run(["pactl", "list", "short", "sources"])
        if code != 0:
            return []
        items: List[Tuple[str, str]] = []
        for line in out.splitlines():
            # Format: index\tname\tmodule\tsampleSpec\tstate
            parts = line.split('\t')
            if len(parts) >= 2:
                name = parts[1]
                items.append((name, name))
        return items
    except FileNotFoundError:
        return []


def get_default_monitor_source() -> str:
    """Pick the default sink's .monitor if available; otherwise the first *.monitor source; else 'default'."""
    try:
        code, sink_name, _ = run(["pactl", "get-default-sink"])
        sink_name = sink_name.strip()
        if code == 0 and sink_name:
            candidate = f"{sink_name}.monitor"
            sources = [s for s, _ in list_pulse_sources()]
            if candidate in sources:
                return candidate
        # fallback: first *.monitor source
        for s, _ in list_pulse_sources():
            if s.endswith(".monitor"):
                return s
    except Exception:
        pass
    return "default"


def record_once(source: str, out_wav: str, sample_rate: int, channels: int, duration: Optional[int]) -> None:
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


def segment_and_transcribe_live(source: str, sample_rate: int, channels: int, segment_seconds: int,
                                engine: str, model_size: str, language: Optional[str], timestamps: bool,
                                output_path: Optional[str]) -> None:
    ffmpeg = which("ffmpeg")
    with tempfile.TemporaryDirectory(prefix="sys2txt_") as tmp:
        pattern = os.path.join(tmp, "seg_%05d.wav")
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
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-reset_timestamps",
            "1",
            pattern,
        ]

        print(f"Live mode: segmenting every {segment_seconds}s from '{source}'. Press Ctrl-C to stop.")
        proc = subprocess.Popen(args)
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
                    text = transcribe_file(full, engine=engine, model_size=model_size, language=language,
                                            timestamps=timestamps)
                    if timestamps:
                        # Derive rough segment time window from filename index
                        try:
                            idx = int(os.path.splitext(f)[0].split("_")[-1])
                            start = idx * segment_seconds
                            end = start + segment_seconds
                            prefix = f"[{start:>5d}-{end:>5d}s] "
                        except Exception:
                            prefix = ""
                        line = prefix + text.strip()
                    else:
                        line = text.strip()
                    print(line, flush=True)
                    if output_path:
                        with open(output_path, "a", encoding="utf-8") as w:
                            w.write(line + "\n")

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
                        text = transcribe_file(full, engine=engine, model_size=model_size, language=language,
                                                timestamps=timestamps)
                        print(text.strip(), flush=True)
                        if output_path:
                            with open(output_path, "a", encoding="utf-8") as w:
                                w.write(text.strip() + "\n")
                    break
                time.sleep(0.3)
        except KeyboardInterrupt:
            try:
                proc.send_signal(signal.SIGINT)
            except Exception:
                pass
            proc.wait()
            print("Stopped live capture.")


def transcribe_file(path: str, engine: str, model_size: str, language: Optional[str], timestamps: bool) -> str:
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


def main():
    parser = argparse.ArgumentParser(description="Record Ubuntu system audio and transcribe with Whisper.")
    sub = parser.add_subparsers(dest="mode", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--source", help="PulseAudio source name (e.g., <sink>.monitor). Defaults to auto.", default=None)
    common.add_argument("--model", dest="model_size", default="small",
                        choices=["tiny", "base", "small", "medium", "large-v2"],
                        help="Whisper model size (default: small)")
    common.add_argument("--engine", choices=["auto", "faster", "whisper"], default="auto",
                        help="Transcription engine (default: auto)")
    common.add_argument("--language", default=None, help="Force language code (e.g., en). Defaults to auto-detect")
    common.add_argument("--timestamps", action="store_true", help="Print timestamps with transcript")
    common.add_argument("--list-sources", action="store_true", help="List PulseAudio sources and exit")

    once = sub.add_parser("once", parents=[common], help="Record once and transcribe after")
    once.add_argument("--duration", type=int, default=None, help="Record for N seconds instead of Ctrl-C")
    once.add_argument("--output", default=None, help="Write transcript to file")
    once.add_argument("--input", default=None, help="Skip recording and transcribe this existing audio file")

    live = sub.add_parser("live", parents=[common], help="Segmented live transcription")
    live.add_argument("--segment-seconds", type=int, default=8, help="Segment length in seconds (default: 8)")
    live.add_argument("--output", default=None, help="Append live transcript to this file as it’s produced")

    args = parser.parse_args()

    if args.list_sources:
        sources = list_pulse_sources()
        if not sources:
            print("No PulseAudio sources found. Is PulseAudio/PipeWire running?", file=sys.stderr)
            sys.exit(1)
        print("Available PulseAudio sources:")
        for name, _ in sources:
            print("  ", name)
        return

    # Determine source
    source = args.source or get_default_monitor_source()

    if args.mode == "once":
        if args.input:
            audio_path = args.input
        else:
            # Make a temp WAV, record until duration/ctrl-c, then transcribe
            with tempfile.TemporaryDirectory(prefix="sys2txt_") as tmp:
                wav = os.path.join(tmp, "capture.wav")
                record_once(source=source, out_wav=wav, sample_rate=16000, channels=1, duration=args.duration)
                audio_path = wav
                text = transcribe_file(audio_path, engine=args.engine, model_size=args.model_size,
                                       language=args.language, timestamps=args.timestamps)
                print(text)
                if args.output:
                    with open(args.output, "w", encoding="utf-8") as w:
                        w.write(text + "\n")
                return
        # If input provided, just transcribe it
        text = transcribe_file(audio_path, engine=args.engine, model_size=args.model_size,
                               language=args.language, timestamps=args.timestamps)
        print(text)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as w:
                w.write(text + "\n")

    elif args.mode == "live":
        segment_and_transcribe_live(source=source, sample_rate=16000, channels=1,
                                    segment_seconds=args.segment_seconds, engine=args.engine,
                                    model_size=args.model_size, language=args.language,
                                    timestamps=args.timestamps, output_path=args.output)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
