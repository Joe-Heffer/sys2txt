"""Transcript data types and the output formats they can be rendered as.

A transcript is a sequence of :class:`Cue` values: timed spans of speech measured in
seconds from the start of the recording. Rendering them is separate from producing
them, so any engine can feed any format.

Four of the five formats are the ones the speech-to-text ecosystem has settled on:
WebVTT is a W3C standard, SubRip (SRT) is the de-facto subtitle format, and the JSON
and TSV layouts match what openai-whisper's own CLI writes. ``txt`` is sys2txt's
original plain-text output, kept as the default.

Nothing here prints or writes files: renderers return strings and the caller decides
where they go.
"""

import json
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

OUTPUT_FORMATS = ("txt", "srt", "vtt", "json", "tsv")
"Output formats a transcript can be rendered as"

FORMAT_EXTENSIONS: Dict[str, str] = {
    "txt": ".txt",
    "srt": ".srt",
    "vtt": ".vtt",
    "json": ".json",
    "tsv": ".tsv",
}
"File extension to use for each output format"

TIMED_FORMATS = ("srt", "vtt", "json", "tsv")
"Formats that carry cue timings of their own, so ``--timestamps`` adds nothing"


@dataclass(frozen=True)
class Cue:
    """One timed span of transcribed speech.

    Attributes:
        start: Start of the span in seconds from the beginning of the recording
        end: End of the span in seconds from the beginning of the recording
        text: Transcribed text of the span
    """

    start: float
    end: float
    text: str

    def shifted(self, offset: float) -> "Cue":
        """Return this cue moved along the timeline by ``offset`` seconds."""
        return Cue(start=self.start + offset, end=self.end + offset, text=self.text)


@dataclass(frozen=True)
class Transcript:
    """A transcribed audio file.

    Attributes:
        cues: Timed spans of speech, in chronological order
        language: Language code the engine detected or was told to use, when known
    """

    cues: Tuple[Cue, ...] = ()
    language: Optional[str] = None

    @property
    def text(self) -> str:
        """The transcript as a single line of plain text."""
        return " ".join(cue.text.strip() for cue in self.cues if cue.text.strip()).strip()


def format_timestamp(seconds: float, *, decimal_separator: str = ".") -> str:
    """Format a number of seconds as ``HH:MM:SS.mmm``.

    Args:
        seconds: Time in seconds. Negative values are clamped to zero.
        decimal_separator: Separator before the milliseconds. SubRip requires ``","``,
            WebVTT requires ``"."``.

    Returns:
        A timestamp string with two-digit hours, which both SubRip and WebVTT accept.
    """
    if seconds < 0:
        seconds = 0.0
    milliseconds = round(seconds * 1000)
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    secs, milliseconds = divmod(milliseconds, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}{decimal_separator}{milliseconds:03d}"


def _escape_vtt(text: str) -> str:
    """Escape the characters WebVTT reads as cue markup."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class TranscriptFormatter:
    """Renders cues into a transcript document, one piece at a time.

    A document is ``header()``, then one ``cue()`` per cue, then ``footer()``. Formats
    that can be written incrementally return each cue from ``cue()``; ``json`` has to
    see every cue before it can be serialized, so it buffers and returns the whole
    document from ``footer()``. Either way the concatenation is the finished document,
    which is what lets live mode stream and once mode render in one go.

    Args:
        timestamps: Include timings in plain-text output. Ignored by timed formats.
        language: Language code to record in formats that have somewhere to put it.
    """

    def __init__(self, *, timestamps: bool = False, language: Optional[str] = None) -> None:
        self.timestamps = timestamps
        self.language = language

    def header(self) -> str:
        """Return the text that opens the document."""
        return ""

    def cue(self, cue: Cue) -> str:
        """Return the text for one cue, which may be empty if the format skips it."""
        raise NotImplementedError

    def footer(self) -> str:
        """Return the text that closes the document."""
        return ""


class _TxtFormatter(TranscriptFormatter):
    """sys2txt's original plain-text output.

    Without timings the whole transcript is one space-separated line; with them it is
    one line per cue. The separator goes before each cue rather than after it so the
    document never ends in trailing whitespace.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._emitted = False

    def cue(self, cue: Cue) -> str:
        text = cue.text.strip()
        if self.timestamps:
            chunk = f"[{cue.start:6.2f}-{cue.end:6.2f}] {text}"
        elif text:
            chunk = text
        else:
            return ""
        separator = ("\n" if self.timestamps else " ") if self._emitted else ""
        self._emitted = True
        return separator + chunk


class _CueBlockFormatter(TranscriptFormatter):
    """Shared behaviour for the two subtitle formats, which differ only in detail."""

    decimal_separator = "."
    numbered = False

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._count = 0

    def cue(self, cue: Cue) -> str:
        text = cue.text.strip()
        if not text:
            # A subtitle cue with no text is noise, and silence needs no cue at all.
            return ""
        self._count += 1
        start = format_timestamp(cue.start, decimal_separator=self.decimal_separator)
        end = format_timestamp(max(cue.end, cue.start), decimal_separator=self.decimal_separator)
        number = f"{self._count}\n" if self.numbered else ""
        return f"{number}{start} --> {end}\n{self._render_text(text)}\n\n"

    def _render_text(self, text: str) -> str:
        return text


class _SrtFormatter(_CueBlockFormatter):
    """SubRip (``.srt``): the de-facto subtitle format, understood by every player."""

    decimal_separator = ","
    numbered = True


class _VttFormatter(_CueBlockFormatter):
    """WebVTT (``.vtt``): the W3C standard, consumed natively by browsers."""

    decimal_separator = "."
    numbered = False

    def header(self) -> str:
        return "WEBVTT\n\n"

    def _render_text(self, text: str) -> str:
        return _escape_vtt(text)


class _TsvFormatter(TranscriptFormatter):
    """Tab-separated milliseconds and text, matching openai-whisper's TSV writer."""

    def header(self) -> str:
        return "start\tend\ttext\n"

    def cue(self, cue: Cue) -> str:
        text = " ".join(cue.text.split())
        if not text:
            return ""
        start = round(max(cue.start, 0.0) * 1000)
        end = round(max(cue.end, cue.start, 0.0) * 1000)
        return f"{start}\t{end}\t{text}\n"


class _JsonFormatter(TranscriptFormatter):
    """openai-whisper's JSON shape, so existing tooling reads sys2txt output unchanged.

    Cues have to be buffered: the document cannot be closed until the last one arrives.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._cues: List[Cue] = []

    def cue(self, cue: Cue) -> str:
        if cue.text.strip():
            self._cues.append(cue)
        return ""

    def footer(self) -> str:
        segments = [
            {
                "id": index,
                "start": round(cue.start, 3),
                "end": round(max(cue.end, cue.start), 3),
                "text": cue.text.strip(),
            }
            for index, cue in enumerate(self._cues)
        ]
        document = {
            "text": " ".join(segment["text"] for segment in segments).strip(),
            "segments": segments,
            "language": self.language,
        }
        return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


_FORMATTERS = {
    "txt": _TxtFormatter,
    "srt": _SrtFormatter,
    "vtt": _VttFormatter,
    "json": _JsonFormatter,
    "tsv": _TsvFormatter,
}


def get_formatter(
    output_format: str, *, timestamps: bool = False, language: Optional[str] = None
) -> TranscriptFormatter:
    """Build the formatter for an output format.

    Args:
        output_format: One of :data:`OUTPUT_FORMATS`
        timestamps: Include timings in plain-text output
        language: Language code to record where the format allows it

    Returns:
        A formatter ready to render a document

    Raises:
        ValueError: If the output format is not one of :data:`OUTPUT_FORMATS`
    """
    try:
        formatter_class = _FORMATTERS[output_format]
    except KeyError:
        raise ValueError(f"Unknown output format: {output_format}") from None
    return formatter_class(timestamps=timestamps, language=language)


def render_transcript(
    cues: Iterable[Cue],
    output_format: str = "txt",
    *,
    timestamps: bool = False,
    language: Optional[str] = None,
) -> str:
    """Render cues as a complete transcript document.

    Args:
        cues: Timed spans of speech, in chronological order
        output_format: One of :data:`OUTPUT_FORMATS`
        timestamps: Include timings in plain-text output. Ignored by timed formats,
            which always carry their own.
        language: Language code to record where the format allows it

    Returns:
        The finished document

    Raises:
        ValueError: If the output format is not one of :data:`OUTPUT_FORMATS`
    """
    formatter = get_formatter(output_format, timestamps=timestamps, language=language)
    parts = [formatter.header()]
    parts.extend(formatter.cue(cue) for cue in cues)
    parts.append(formatter.footer())
    return "".join(parts)
