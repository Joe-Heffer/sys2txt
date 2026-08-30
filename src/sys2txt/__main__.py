#!/usr/bin/env python3
"""Main entry point for sys2txt CLI."""

import argparse
import contextlib
import copy
import logging
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, TextIO

from . import __version__
from .constants import (
    DEFAULT_OUTPUT_FORMAT,
    DEFAULT_SEGMENT_SECONDS,
    DEFAULT_WHISPER_MODEL,
    MAX_CONSECUTIVE_SEGMENT_FAILURES,
    get_default_whisper_model,
)
from .engines import ENGINE_NAMES
from .formats import FORMAT_EXTENSIONS, OUTPUT_FORMATS, TIMED_FORMATS, get_formatter, render_transcript
from .pipeline import TranscriptSegment, transcribe_live, transcribe_once_cues
from .pulse import get_default_monitor_source, list_pulse_sources
from .transcribe import TranscriptionConfig, transcribe_file_cues

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Options:
    """Validated CLI options. The boundary between argument parsing and behaviour."""

    mode: str
    source: Optional[str] = None
    model: str = DEFAULT_WHISPER_MODEL
    engine: str = "auto"
    device: str = "auto"
    language: Optional[str] = None
    timestamps: bool = False
    list_sources: bool = False
    model_path: Optional[str] = None
    whisper_cpp_path: Optional[str] = None
    download_model: bool = True
    output: Optional[str] = None
    duration: Optional[int] = None
    input_path: Optional[str] = None
    segment_seconds: int = DEFAULT_SEGMENT_SECONDS
    silence_timeout: int = 0
    max_lag: float = 0.0
    on_lag: str = "drop"
    output_format: str = DEFAULT_OUTPUT_FORMAT


def get_timestamp_filename(extension: str = ".txt") -> str:
    """Generate a timestamp-based filename for output files.

    Args:
        extension: File extension to append, including the leading dot

    Returns:
        A filename string in the format: YYYY-MM-DD_HH-MM-SS<extension>
    """
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + extension


def ensure_output_dir() -> str:
    """Ensure the output directory exists and return its path.

    Returns:
        Absolute path to the output directory
    """
    output_dir = os.path.join(os.getcwd(), "output")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def _resolve_output_path(output_arg: Optional[str], output_format: str = DEFAULT_OUTPUT_FORMAT) -> str:
    """Return the output file path, generating a timestamped name if none given.

    A generated name takes the extension of the output format; an explicit path is used
    as given, on the assumption the caller named it deliberately.
    """
    if output_arg:
        return output_arg
    output_dir = ensure_output_dir()
    return os.path.join(output_dir, get_timestamp_filename(FORMAT_EXTENSIONS[output_format]))


def _build_options(args: argparse.Namespace) -> Options:
    """Convert parsed arguments into validated Options.

    Raises:
        ValueError: If the arguments are inconsistent or refer to a missing file
    """
    input_path = getattr(args, "input", None)
    duration = getattr(args, "duration", None)
    segment_seconds = getattr(args, "segment_seconds", DEFAULT_SEGMENT_SECONDS)
    silence_timeout = getattr(args, "silence_timeout", 0)
    max_lag = getattr(args, "max_lag", 0.0)
    on_lag = getattr(args, "on_lag", None)

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
    if max_lag < 0:
        raise ValueError(f"--max-lag must not be negative, got {max_lag}")
    if 0 < max_lag < segment_seconds:
        raise ValueError(
            f"--max-lag ({max_lag:g}s) must be at least --segment-seconds ({segment_seconds}s), "
            "since the backlog is only measured a whole segment at a time"
        )
    if on_lag is not None and max_lag <= 0:
        raise ValueError(f"--on-lag {on_lag} needs a --max-lag to say how far behind is too far")

    output_format = getattr(args, "output_format", DEFAULT_OUTPUT_FORMAT)
    if args.timestamps and output_format in TIMED_FORMATS:
        logger.warning("--timestamps has no effect with --format %s, which always carries times", output_format)

    if args.engine not in ("cpp", "auto"):
        if args.model_path:
            logger.warning("--model-path is only used with --engine cpp")
        if args.whisper_cpp_path:
            logger.warning("--whisper-cpp-path is only used with --engine cpp")
        if args.no_download:
            logger.warning("--no-download is only used with --engine cpp")

    if args.device in ("vulkan", "gpu") and args.engine != "cpp":
        logger.warning(
            "--device %s is only honoured by --engine cpp; engine %s will fall back to CPU",
            args.device,
            args.engine,
        )
    if args.device == "cuda" and args.engine == "cpp":
        logger.warning("--device cuda is not a whisper.cpp device; --engine cpp will use GPU if available, else CPU")

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
        download_model=not args.no_download,
        output=args.output,
        duration=duration,
        input_path=input_path,
        segment_seconds=segment_seconds,
        silence_timeout=silence_timeout,
        max_lag=max_lag,
        on_lag=on_lag or "drop",
        output_format=output_format,
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
        download_model=options.download_model,
        device=options.device,
    )


def _check_output_writable(output_file: str) -> None:
    """Fail fast if output_file cannot be written to, before recording or transcription starts.

    Raises:
        RuntimeError: If the path's directory is missing or the file cannot be opened for writing
    """
    directory = os.path.dirname(output_file) or "."
    if not os.path.isdir(directory):
        raise RuntimeError(f"--output directory does not exist: {directory}")
    try:
        with open(output_file, "a", encoding="utf-8"):
            pass
    except OSError as e:
        raise RuntimeError(f"--output path is not writable: {output_file} ({e})") from e


def _save_transcript(text: str, output_file: str) -> None:
    """Print transcript, write it to output_file, and log the saved path.

    The document ends in exactly one newline, whether or not the format supplied its own.
    """
    document = text if text.endswith("\n") else text + "\n"
    print(document, end="")
    with open(output_file, "w", encoding="utf-8") as w:
        w.write(document)
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
        record = copy.copy(record)
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)


_LEVEL_NAMES = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


def _configure_logging(verbose: bool, quiet: bool) -> None:
    """Configure logging based on CLI flags, falling back to SYS2TXT_LOG_LEVEL, then a default.

    Precedence: explicit --verbose/--quiet > SYS2TXT_LOG_LEVEL > default (WARNING).
    """
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level_name = os.environ.get("SYS2TXT_LOG_LEVEL", "").upper()
        if level_name in _LEVEL_NAMES:
            level = getattr(logging, level_name)
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
    for existing in list(root.handlers):
        root.removeHandler(existing)
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
    default_model = get_default_whisper_model()
    common.add_argument(
        "--model",
        dest="model_size",
        default=default_model,
        help=f"Whisper model size (default: {default_model})",
    )
    common.add_argument(
        "--engine",
        choices=list(ENGINE_NAMES),
        default="auto",
        help="Transcription engine (default: auto)",
    )
    common.add_argument("--language", default=None, help="Force language code (e.g., en). Defaults to auto-detect")
    common.add_argument("--timestamps", action="store_true", help="Print timestamps with transcript")
    common.add_argument(
        "--format",
        dest="output_format",
        choices=list(OUTPUT_FORMATS),
        default=DEFAULT_OUTPUT_FORMAT,
        help=(
            "Transcript format: txt (plain text), srt (SubRip subtitles), vtt (WebVTT subtitles), "
            f"json (openai-whisper schema), tsv (default: {DEFAULT_OUTPUT_FORMAT})"
        ),
    )
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
    common.add_argument(
        "--no-download",
        action="store_true",
        help="Don't automatically download a missing whisper.cpp model file (for cpp engine)",
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
    live.add_argument(
        "--max-lag",
        type=float,
        default=0.0,
        metavar="SECONDS",
        help=(
            "Seconds of untranscribed audio to tolerate before --on-lag applies "
            "(0=unlimited, default: 0). Falling behind is always warned about"
        ),
    )
    live.add_argument(
        "--on-lag",
        choices=["drop", "fail"],
        default=None,
        help=(
            "What to do once the backlog exceeds --max-lag: drop the oldest segments to catch "
            "up, or stop with an error (default: drop). Requires --max-lag"
        ),
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
    output_file = _resolve_output_path(options.output, options.output_format)
    _check_output_writable(output_file)
    config = _build_transcription_config(options)

    if options.input_path:
        transcript = transcribe_file_cues(options.input_path, config)
    else:
        transcript = transcribe_once_cues(source, config, options.duration)

    text = render_transcript(
        transcript.cues,
        options.output_format,
        timestamps=options.timestamps,
        language=transcript.language,
    )
    _save_transcript(text, output_file)


def _emit(chunk: str, handle: TextIO) -> None:
    """Print one piece of a transcript document and append it to the open output file."""
    if not chunk:
        return
    print(chunk, end="", flush=True)
    handle.write(chunk)
    handle.flush()


def _run_live(options: Options, source: str) -> None:
    """Consume live transcript segments, printing and saving each one as it arrives."""
    output_file = _resolve_output_path(options.output, options.output_format)
    _check_output_writable(output_file)
    config = _build_transcription_config(options)
    logger.info("Live transcript will be saved to: %s", output_file)
    logger.info("Press Ctrl-C once to stop live capture and save the transcript.")

    # Plain text is a running log that can be appended to. The other formats are documents
    # with their own header, cue numbering and syntax, so each run starts a fresh one.
    formatter = (
        None if options.output_format == "txt" else get_formatter(options.output_format, language=options.language)
    )

    # Only the drop policy is the recorder's business; failing is a decision about the run.
    max_lag = options.max_lag if options.on_lag == "drop" else 0.0
    segments = transcribe_live(source, config, segment_seconds=options.segment_seconds, max_lag=max_lag)
    silence_start: Optional[float] = None
    failures = 0
    failure: Optional[str] = None
    with open(output_file, "a" if formatter is None else "w", encoding="utf-8") as handle:
        if formatter is not None:
            _emit(formatter.header(), handle)
        try:
            with contextlib.closing(segments):
                for segment in segments:
                    if formatter is None:
                        line = _format_segment(segment, options.timestamps)
                        print(line, flush=True)
                        handle.write(line + "\n")
                        handle.flush()
                    else:
                        for cue in segment.cues:
                            _emit(formatter.cue(cue), handle)

                    if segment.dropped:
                        # Dropped audio says nothing about what was said in it, so it neither
                        # counts as speech nor accumulates towards the silence timeout.
                        silence_start = None

                    if options.on_lag == "fail" and 0 < options.max_lag < segment.lag:
                        failure = (
                            f"Transcription fell {segment.lag:.0f}s behind, past the "
                            f"--max-lag of {options.max_lag:g}s, stopping."
                        )
                        break

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
        if formatter is not None:
            # Closes the document, so it has to run whether capture ended, timed out or
            # was interrupted. JSON in particular is written entirely from here.
            _emit(formatter.footer(), handle)

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
