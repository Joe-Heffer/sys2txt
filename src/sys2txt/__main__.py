#!/usr/bin/env python3
"""Main entry point for sys2txt CLI."""

import argparse
import os
import sys
import tempfile

from .audio import record_once, segment_and_transcribe_live
from .pulse import get_default_monitor_source, list_pulse_sources
from .transcribe import transcribe_file


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Record Ubuntu system audio and transcribe with Whisper.")
    sub = parser.add_subparsers(dest="mode", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--source", help="PulseAudio source name (e.g., <sink>.monitor). Defaults to auto.", default=None
    )
    common.add_argument(
        "--model",
        dest="model_size",
        default="small",
        help="Whisper model size (default: small)",
    )
    common.add_argument(
        "--engine", choices=["auto", "faster", "whisper"], default="auto", help="Transcription engine (default: auto)"
    )
    common.add_argument("--language", default=None, help="Force language code (e.g., en). Defaults to auto-detect")
    common.add_argument("--timestamps", action="store_true", help="Print timestamps with transcript")
    common.add_argument("--list-sources", action="store_true", help="List PulseAudio sources and exit")

    once = sub.add_parser("once", parents=[common], help="Record once and transcribe after")
    once.add_argument("--duration", type=int, default=None, help="Record for N seconds instead of Ctrl-C")
    once.add_argument("--output", default=None, help="Write transcript to file")
    once.add_argument("--input", default=None, help="Skip recording and transcribe this existing audio file")

    live = sub.add_parser("live", parents=[common], help="Segmented live transcription")
    live.add_argument("--segment-seconds", type=int, default=8, help="Segment length in seconds (default: 8)")
    live.add_argument("--output", default=None, help="Append live transcript to this file as it's produced")

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
                text = transcribe_file(
                    audio_path,
                    engine=args.engine,
                    model_size=args.model_size,
                    language=args.language,
                    timestamps=args.timestamps,
                )
                print(text)
                if args.output:
                    with open(args.output, "w", encoding="utf-8") as w:
                        w.write(text + "\n")
                return
        # If input provided, just transcribe it
        text = transcribe_file(
            audio_path,
            engine=args.engine,
            model_size=args.model_size,
            language=args.language,
            timestamps=args.timestamps,
        )
        print(text)
        if args.output:
            with open(args.output, "w", encoding="utf-8") as w:
                w.write(text + "\n")

    elif args.mode == "live":

        def transcribe_segment(file_path: str, segment_index: int) -> str:
            """Transcribe a segment and format with optional timestamp prefix."""
            text = transcribe_file(
                file_path,
                engine=args.engine,
                model_size=args.model_size,
                language=args.language,
                timestamps=args.timestamps,
            )
            if args.timestamps:
                # Add segment time window prefix
                start = segment_index * args.segment_seconds
                end = start + args.segment_seconds
                prefix = f"[{start:>5d}-{end:>5d}s] "
                return prefix + text.strip()
            else:
                return text.strip()

        segment_and_transcribe_live(
            source=source,
            sample_rate=16000,
            channels=1,
            segment_seconds=args.segment_seconds,
            transcribe_callback=transcribe_segment,
            output_path=args.output,
        )


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
