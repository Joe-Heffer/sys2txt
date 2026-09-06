# Output formats

`--format` picks how the transcript is written, and applies to stdout and the output file alike.

| Format | Extension | What it is |
| --- | --- | --- |
| `txt` | `.txt` | Plain text, the default. One line per segment in live mode |
| `srt` | `.srt` | [SubRip](https://en.wikipedia.org/wiki/SubRip) subtitles, understood by essentially every video player |
| `vtt` | `.vtt` | [WebVTT](https://www.w3.org/TR/webvtt1/), the W3C standard, loadable by a browser `<track>` element |
| `json` | `.json` | openai-whisper's JSON schema (`text`, `segments`, `language`), for programmatic use |
| `tsv` | `.tsv` | Tab-separated `start`/`end` milliseconds and text |

The timed formats carry the engine's own per-utterance timings. In live mode those are rebased onto
the timeline of the whole recording, so cue times keep increasing across segments.
