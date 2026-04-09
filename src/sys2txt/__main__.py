#!/usr/bin/env python3
"""Main entry point for sys2txt CLI."""

import argparse
import logging
import os
import sys
import tempfile
from datetime import datetime

from .audio import record_once, segment_and_transcribe_live
from .constants import WHISPER_MODEL
from .pulse import get_default_monitor_source, list_pulse_sources
from .transcribe import transcribe_file


def get_timestamp_filename() -> str:
    """Generate a timestamp-based filename for output files.

    Returns:
        A filename string in the format: YYYY-MM-DD_HH-MM-SS.txt
    """
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S.txt")


def ensure_output_dir() -> str:
    """Ensure the output directory exists and return its path.

    Returns:
        Absolute path to the output directory
    """
    output_dir = os.path.join(os.getcwd(), "output")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


logger = logging.getLogger(__name__)


def _resolve_output_path(output_arg: str | None) -> str:
    """Return the output file path, generating a timestamped name if none given."""
    output_dir = ensure_output_dir()
    return output_arg if output_arg else os.path.join(output_dir, get_timestamp_filename())


def _build_transcribe_kwargs(args) -> dict:
    """Build the common keyword arguments for transcribe_file() from parsed args."""
    return dict(
        engine=args.engine,
        model_size=args.model_size,
        language=args.language,
        timestamps=args.timestamps,
        model_path=args.model_path,
        whisper_cpp_path=args.whisper_cpp_path,
        device=args.device,
    )


def _save_transcript(text: str, output_file: str) -> None:
    """Print transcript, write it to output_file, and log the saved path."""
    print(text)
    with open(output_file, "w", encoding="utf-8") as w:
        w.write(text + "\n")
    logger.info("Transcript saved to: %s", output_file)


def _configure_logging(verbose: bool, quiet: bool) -> None:
    """Configure logging based on CLI flags and LOG_LEVEL environment variable."""
    level_name = os.environ.get("LOG_LEVEL", "").upper()
    if level_name and hasattr(logging, level_name):
        level = getattr(logging, level_name)
    elif quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s", stream=sys.stderr)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Record Ubuntu system audio and transcribe with Whisper.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose (debug) logging")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress informational log messages")
    sub = parser.add_subparsers(dest="mode", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--source", help="PulseAudio source name (e.g., <sink>.monitor). Defaults to auto.", default=None
    )
    common.add_argument(
        "--model",
        dest="model_size",
        default=WHISPER_MODEL,
        help=f"Whisper model size (default: {WHISPER_MODEL})",
    )
    common.add_argument(
        "--engine",
        choices=["auto", "faster", "whisper", "cpp"],
        default="auto",
        help="Transcription engine (default: auto)",
    )
    common.add_argument("--language", default=None, help="Force language code (e.g., en). Defaults to auto-detect")
    common.add_argument("--timestamps", action="store_true", help="Print timestamps with transcript")
    common.add_argument("--list-sources", action="store_true", help="List PulseAudio sources and exit")
    common.add_argument(
        "--device",
        choices=["auto", "cpu", "vulkan", "gpu", "cuda"],
        default="auto",
        help=(
            "Device for transcription: cpu (force CPU), cuda (NVIDIA, faster-whisper only), "
            "vulkan/gpu (AMD/Vulkan, whisper.cpp only), auto (default, let engine decide)"
        ),
    )
    common.add_argument(
        "--model-path",
        default=None,
        help="Path to whisper.cpp model file (for cpp engine)",
    )
    common.add_argument(
        "--whisper-cpp-path",
        default=None,
        help="Path to whisper-cli binary (for cpp engine)",
    )

    once = sub.add_parser("once", parents=[common], help="Record once and transcribe after")
    once.add_argument("--duration", type=int, default=None, help="Record for N seconds instead of Ctrl-C")
    once.add_argument("--output", default=None, help="Write transcript to file")
    once.add_argument("--input", default=None, help="Skip recording and transcribe this existing audio file")

    live = sub.add_parser("live", parents=[common], help="Segmented live transcription")
    live.add_argument("--segment-seconds", type=int, default=8, help="Segment length in seconds (default: 8)")
    live.add_argument("--output", default=None, help="Append live transcript to this file as it's produced")
    live.add_argument(
        "--silence-timeout",
        type=int,
        default=0,
        help="Auto-stop after N consecutive seconds of silence (0=disabled, default: 0)",
    )

    args = parser.parse_args()

    _configure_logging(verbose=args.verbose, quiet=args.quiet)

    if args.engine not in ("cpp", "auto"):
        if args.model_path:
            logger.warning("--model-path is only used with --engine cpp")
        if args.whisper_cpp_path:
            logger.warning("--whisper-cpp-path is only used with --engine cpp")

    if args.list_sources:
        sources = list_pulse_sources()
        if not sources:
            logger.error("No PulseAudio sources found. Is PulseAudio/PipeWire running?")
            sys.exit(1)
        print("Available PulseAudio sources:")
        for name, _ in sources:
            print("  ", name)
        return

    # Determine source
    source = args.source or get_default_monitor_source()

    if args.mode == "once":
        output_file = _resolve_output_path(args.output)
        transcribe_kwargs = _build_transcribe_kwargs(args)

        if args.input:
            text = transcribe_file(args.input, **transcribe_kwargs)
        else:
            with tempfile.TemporaryDirectory(prefix="sys2txt_") as tmp:
                wav = os.path.join(tmp, "capture.wav")
                record_once(source=source, out_wav=wav, sample_rate=16000, channels=1, duration=args.duration)
                text = transcribe_file(wav, **transcribe_kwargs)

        _save_transcript(text, output_file)

    elif args.mode == "live":
        output_file = _resolve_output_path(args.output)
        transcribe_kwargs = _build_transcribe_kwargs(args)
        logger.info("Live transcript will be saved to: %s", output_file)

        def transcribe_segment(file_path: str, segment_index: int) -> str:
            """Transcribe a segment and format with optional timestamp prefix."""
            text = transcribe_file(file_path, **transcribe_kwargs)
            if args.timestamps:
                start = segment_index * args.segment_seconds
                end = start + args.segment_seconds
                prefix = f"[{start:>5d}-{end:>5d}s] "
                return prefix + text.strip()
            return text.strip()

        segment_and_transcribe_live(
            source=source,
            sample_rate=16000,
            channels=1,
            segment_seconds=args.segment_seconds,
            transcribe_callback=transcribe_segment,
            output_path=output_file,
            silence_timeout=args.silence_timeout,
        )


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        logger.error("%s", e)
        sys.exit(1)
    except KeyboardInterrupt:
        pass
