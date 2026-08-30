"""Configuration values shared by the library and the CLI."""

import os

DEFAULT_WHISPER_MODEL = "small.en"
"Fallback Whisper model when SYS2TXT_WHISPER_MODEL is not set"


def get_default_whisper_model() -> str:
    """Return the default Whisper model, read fresh from SYS2TXT_WHISPER_MODEL each call."""
    return os.getenv("SYS2TXT_WHISPER_MODEL", DEFAULT_WHISPER_MODEL)


SAMPLE_RATE = 16000
"Capture sample rate in Hz. Whisper models expect 16 kHz audio."

CHANNELS = 1
"Number of capture channels. Whisper models expect mono audio."

DEFAULT_SEGMENT_SECONDS = 8
"Default length of a live-mode segment in seconds"

MIN_SEGMENT_BYTES = 64
"Segments smaller than this are header-only and hold no audio"

SEGMENT_POLL_INTERVAL = 0.3
"Seconds to wait between scans of the segment directory"

FFMPEG_SHUTDOWN_GRACE = 3.0
"Seconds to wait for ffmpeg to exit after asking it to quit, before terminating it"

TRANSCRIBE_TIMEOUT_FACTOR = 5
"Segment transcription is allowed this multiple of the segment length"

MIN_TRANSCRIBE_TIMEOUT = 60
"Lower bound in seconds for the per-segment transcription timeout"

WHISPER_CPP_TIMEOUT = 300
"Seconds to wait for whisper-cli before assuming a GPU hang or malformed audio"

LAG_WARN_FACTOR = 2
"Live mode warns that it is falling behind once the backlog exceeds this many segments"

MAX_CONSECUTIVE_SEGMENT_FAILURES = 3
"Consecutive live-mode transcription failures tolerated before giving up"

DEFAULT_OUTPUT_FORMAT = "txt"
"Default transcript output format. See sys2txt.formats.OUTPUT_FORMATS for the rest."
