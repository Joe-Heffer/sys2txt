"""Record system audio and transcribe it to text.

The public API is small: enumerate sources with :func:`list_pulse_sources` or
:func:`get_default_monitor_source`, then either transcribe a single recording with
:func:`transcribe_once` or consume a live recording segment by segment with
:func:`transcribe_live`. Either can be rendered as plain text, SubRip, WebVTT, JSON or
TSV with :func:`render_transcript`.

    from sys2txt import TranscriptionConfig, get_default_monitor_source, transcribe_live

    config = TranscriptionConfig(model="small.en")
    for segment in transcribe_live(get_default_monitor_source(), config):
        print(segment.start, segment.text)
"""

from importlib.metadata import PackageNotFoundError, version

from .audio import AudioSegment, iter_audio_segments, record_once
from .formats import OUTPUT_FORMATS, Cue, Transcript, render_transcript
from .pipeline import TranscriptSegment, transcribe_live, transcribe_once, transcribe_once_cues
from .pulse import get_default_monitor_source, list_pulse_sources
from .transcribe import TranscriptionConfig, transcribe_file, transcribe_file_cues

try:
    __version__ = version("sys2txt")
except PackageNotFoundError:  # running from a source tree without an installed distribution
    __version__ = "0.0.0+unknown"

__all__ = [
    "AudioSegment",
    "Cue",
    "OUTPUT_FORMATS",
    "Transcript",
    "TranscriptSegment",
    "TranscriptionConfig",
    "__version__",
    "get_default_monitor_source",
    "iter_audio_segments",
    "list_pulse_sources",
    "record_once",
    "render_transcript",
    "transcribe_file",
    "transcribe_file_cues",
    "transcribe_live",
    "transcribe_once",
    "transcribe_once_cues",
]
