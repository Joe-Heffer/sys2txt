#!/usr/bin/env python3
"""Main entry point for sys2txt CLI."""

import argparse
import contextlib
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from . import __version__
from .constants import DEFAULT_SEGMENT_SECONDS, MAX_CONSECUTIVE_SEGMENT_FAILURES, WHISPER_MODEL
from .pipeline import TranscriptSegment, transcribe_live, transcribe_once
from .pulse import get_default_monitor_source, list_pulse_sources
from .transcribe import TranscriptionConfig, transcribe_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Options:
    """Validated CLI options. The boundary between argument parsing and behaviour."""

    mode: str
    source: Optional[str] = None
    model: str = WHISPER_MODEL
    engine: str = "auto"
    device: str = "auto"
    language: Optional[str] = None
    timestamps: bool = False
    list_sources: bool = False
    model_path: Optional[str] = None
    whisper_cpp_path: Optional[str] = None
    output: Optional[str] = None
    duration: Optional[int] = None
    input_path: Optional[str] = None
    segment_seconds: int = DEFAULT_SEGMENT_SECONDS
    silence_timeout: int = 0


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


def _resolve_output_path(output_arg: Optional[str]) -> str:
    """Return the output file path, generating a timestamped name if none given."""
    output_dir = ensure_output_dir()
    return output_arg if output_arg else os.path.join(output_dir, get_timestamp_filename())


def _build_options(args: argparse.Namespace) -> Options:
    """Convert parsed arguments into validated Options.

    Raises:
        ValueError: If the arguments are inconsistent or refer to a missing file
    """
    input_path = getattr(args, "input", None)
    duration = getattr(args, "duration", None)
    segment_seconds = getattr(args, "segment_seconds", DEFAULT_SEGMENT_SECONDS)
    silence_timeout = getattr(args, "silence_timeout", 0)

    if input_path and not os.path.isfile(input_path):
        raise ValueError(f"--input file not found: {input_path}")
    if duration is not None and duration <= 0:
        raise ValueError(f"--duration must be a positive number of seconds, got {duration}")
    if segment_seconds <= 0:
        raise ValueError(f"--segment-seconds must be a positive number of seconds, got {segment_seconds}")
    if silence_timeout < 0:
        raise ValueError(f"--silence-timeout must not be negative, got {silence_timeout}")
    if 0 < silence_timeout < segment_seconds:
        raise ValueError(
            f"--silence-timeout ({silence_timeout}s) must be at least --segment-seconds "
            f"({segment_seconds}s), since silence is only measured a whole segment at a time"
        )

    if args.engine not in ("cpp", "auto"):
        if args.model_path:
            logger.warning("--model-path is only used with --engine cpp")
        if args.whisper_cpp_path:
            logger.warning("--whisper-cpp-path is only used with --engine cpp")

    return Options(
        mode=args.mode,
        source=args.source,
        model=args.model_size,
        engine=args.engine,
        device=args.device,
        language=args.language,
        timestamps=args.timestamps,
        list_sources=args.list_sources,
        model_path=args.model_path,
        whisper_cpp_path=args.whisper_cpp_path,
        output=args.output,
        duration=duration,
        input_path=input_path,
        segment_seconds=segment_seconds,
        silence_timeout=silence_timeout,
    )


def _build_transcription_config(options: Options) -> TranscriptionConfig:
    """Build a TranscriptionConfig from validated CLI options."""
    return TranscriptionConfig(
        engine=options.engine,
        model=options.model,
        language=options.language,
        timestamps=options.timestamps,
        model_path=options.model_path,
        whisper_cpp_path=options.whisper_cpp_path,
        device=options.device,
    )


def _save_transcript(text: str, output_file: str) -> None:
    """Print transcript, write it to output_file, and log the saved path."""
    print(text)
    with open(output_file, "w", encoding="utf-8") as w:
        w.write(text + "\n")
    logger.info("Transcript saved to: %s", output_file)


def _format_segment(segment: TranscriptSegment, timestamps: bool) -> str:
    """Render a live transcript segment as a single line of output."""
    text = segment.text.strip()
    if timestamps:
        return f"[{int(segment.start):>5d}-{int(segment.end):>5d}s] {text}"
    return text


class _ColorFormatter(logging.Formatter):
    """Logging formatter that colorizes the level name using ANSI codes."""

    COLORS = {
        logging.DEBUG: "\033[2m",  # dim
        logging.INFO: "\033[32m",  # green
        logging.WARNING: "\033[33m",  # yellow
        logging.ERROR: "\033[31m",  # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


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
        level = logging.WARNING

    handler = logging.StreamHandler(sys.stderr)
    fmt = "%(levelname)s: %(message)s"
    if sys.stderr.isatty():
        handler.setFormatter(_ColorFormatter(fmt))
    else:
        handler.setFormatter(logging.Formatter(fmt))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)


def _build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Record Ubuntu system audio and transcribe with Whisper.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
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
    live.add_argument(
        "--segment-seconds",
        type=int,
        default=DEFAULT_SEGMENT_SECONDS,
        help=f"Segment length in seconds (default: {DEFAULT_SEGMENT_SECONDS})",
    )
    live.add_argument("--output", default=None, help="Append live transcript to this file as it's produced")
    live.add_argument(
        "--silence-timeout",
        type=int,
        default=0,
        help="Auto-stop after N consecutive seconds of silence (0=disabled, default: 0)",
    )

    return parser


def main():
    """Main CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args()

    _configure_logging(verbose=args.verbose, quiet=args.quiet)

    try:
        options = _build_options(args)
    except ValueError as e:
        parser.error(str(e))

    try:
        _run(options)
    except RuntimeError as e:
        logger.error("%s", e)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Interrupted. Exiting.")
        sys.exit(130)


def _list_sources() -> None:
    """Print the available PulseAudio sources, or exit if there are none."""
    sources = list_pulse_sources()
    if not sources:
        logger.error("No PulseAudio sources found. Is PulseAudio/PipeWire running?")
        sys.exit(1)
    print("Available PulseAudio sources:")
    for name, _ in sources:
        print("  ", name)


def _run_once(options: Options, source: str) -> None:
    """Record (or read) a single audio file, transcribe it, and save the transcript."""
    output_file = _resolve_output_path(options.output)
    config = _build_transcription_config(options)

    if options.input_path:
        text = transcribe_file(options.input_path, config)
    else:
        text = transcribe_once(source, config, options.duration)

    _save_transcript(text, output_file)


def _run_live(options: Options, source: str) -> None:
    """Consume live transcript segments, printing and saving each one as it arrives."""
    output_file = _resolve_output_path(options.output)
    config = _build_transcription_config(options)
    logger.info("Live transcript will be saved to: %s", output_file)
    logger.info("Press Ctrl-C once to stop live capture and save the transcript.")

    segments = transcribe_live(source, config, segment_seconds=options.segment_seconds)
    silence_start: Optional[float] = None
    failures = 0
    failure: Optional[str] = None
    with open(output_file, "a", encoding="utf-8") as handle:
        try:
            with contextlib.closing(segments):
                for segment in segments:
                    line = _format_segment(segment, options.timestamps)
                    print(line, flush=True)
                    handle.write(line + "\n")
                    handle.flush()

                    if segment.failed:
                        # A failure says nothing about what the segment held, so it neither
                        # counts as speech nor accumulates towards the silence timeout.
                        failures += 1
                        silence_start = None
                        if failures >= MAX_CONSECUTIVE_SEGMENT_FAILURES:
                            failure = (
                                f"Transcription failed for {failures} consecutive segments ({segment.error}), stopping."
                            )
                            break
                        continue

                    failures = 0
                    if segment.text.strip():
                        silence_start = None
                        continue

                    # Measure silence along the recording's timeline, since segments holding no
                    # audio at all are skipped and the processed ones need not be contiguous.
                    if silence_start is None:
                        silence_start = segment.start
                    silent_seconds = segment.end - silence_start
                    if 0 < options.silence_timeout <= silent_seconds:
                        logger.info("No speech detected for %.0f seconds, stopping automatically.", silent_seconds)
                        break
        except KeyboardInterrupt:
            logger.info("Stopping live capture...")

    logger.info("Transcript saved to: %s", output_file)
    if failure:
        raise RuntimeError(failure)


def _run(options: Options) -> None:
    """Dispatch to the requested mode. Raises KeyboardInterrupt/RuntimeError to caller."""
    if options.list_sources:
        _list_sources()
        return

    source = options.source or get_default_monitor_source()

    if options.mode == "once":
        _run_once(options, source)
    elif options.mode == "live":
        _run_live(options, source)


if __name__ == "__main__":
    main()
