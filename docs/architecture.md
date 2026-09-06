# Architecture

This page is for contributors who want to understand how the pieces fit together before
changing them. It complements [CONTRIBUTING.md](https://github.com/Joe-Heffer/sys2txt/blob/main/CONTRIBUTING.md),
which covers dev setup, tests, and PR expectations.

## Module map

Each module has one job:

| Module | Responsibility |
| --- | --- |
| `audio.py` | Records audio with ffmpeg. Nothing else — no transcription, no printing. |
| `pulse.py` | Enumerates and resolves PulseAudio/PipeWire sources via `pactl`. |
| `engines.py` | The transcription engines, the `TranscriptionEngine` protocol, and the registry that picks between them. |
| `transcribe.py` | Thin entry points over the engine registry (`transcribe_file`, `transcribe_file_cues`). |
| `formats.py` | Transcript data types (`Cue`, `Transcript`) and the txt/srt/vtt/json/tsv renderers. Pure formatting — no engine imports, no I/O. |
| `pipeline.py` | Combines recording and transcription into the `once` and `live` workflows. |
| `constants.py` | Shared defaults: model, sample rate, segment length, timeouts, etc. |
| `utils.py` | Small shared helpers (e.g. `which()`). |
| `__main__.py` | The CLI: argument parsing, validation, and the only module that prints or writes files. |

The dependency direction is one-way: `audio.py` and `formats.py` know nothing about each
other or about engines; `pipeline.py` wires recording, engines, and formats together; and
`__main__.py` is the only layer that talks to the user (stdout, output files, exit codes).
This keeps every layer below the CLI usable as a library — see the
[Python API](python-api.md) page.

## Data flow

### `once` mode

```
record_once() -> WAV file -> transcribe_file_cues() -> render_transcript() -> print / write
```

`pipeline.transcribe_once_cues()` records to a temporary WAV file, hands it to the engine
registry, and returns a `Transcript` (a list of `Cue(start, end, text)` plus the detected
language). `__main__._run_once()` renders that transcript in the requested `--format` and
both prints it and writes it to `--output`, if given. `transcribe_once()` is the plain-text
convenience wrapper used when timed cues aren't needed.

### `live` mode

```
iter_audio_segments() -> transcribe_live() -> TranscriptSegment -> per-segment render -> print / append
```

`audio.iter_audio_segments()` is a generator: it spawns ffmpeg with the segment muxer, polls
for finalized chunks, and yields one `AudioSegment(index, path, lag, dropped)` per chunk. It
knows nothing about transcription.

`pipeline.transcribe_live()` wraps that generator, transcribing each segment on a
single-worker thread pool with a timeout, and yields a `TranscriptSegment` for each one —
even a failed or silent one, so the caller always sees a contiguous timeline. A segment
that times out doesn't block the next one: its worker is abandoned rather than reused.

`__main__._run_live()` consumes that stream, formatting and printing each segment as it
arrives. Plain text is printed and appended to the output file line by line; the timed
formats (srt/vtt/json/tsv) are streamed through a `TranscriptFormatter` from `formats.py`
so the header, cues, and footer stay consistent with a one-shot render. This loop is also
where the stop policies live — silence timeout, consecutive-failure limit, and the
`--max-lag`/`--on-lag` backpressure policy — since they're about when to stop consuming the
stream, not about recording or transcribing.

`AudioSegment.lag` and `.dropped` (surfaced on `TranscriptSegment` too) describe how far
behind the recording transcription has fallen and let the CLI warn or drop old audio to
catch back up, rather than growing an unbounded backlog.

## The engine registry

Every transcription backend implements the same small protocol, defined in `engines.py`:

```python
class TranscriptionEngine(Protocol):
    name: str
    def is_available(self) -> bool: ...
    def transcribe(self, path: str, config: TranscriptionConfig) -> Transcript: ...
    def unload(self) -> None: ...
```

`ENGINES` is a list of instances, in the order `auto` prefers them; `ENGINE_NAMES` derives
the `--engine` CLI choices from that same list. `get_engine(name)`:

- for `"auto"`, returns the first engine whose `is_available()` is `True`, raising a
  `RuntimeError` naming every engine it tried if none is installed;
- for a specific name, returns that engine without checking availability, so a
  deliberately-chosen backend reports its own diagnostic (e.g. a missing dependency) rather
  than a generic "not available" message;
- for anything else, raises `ValueError`.

Backends import their heavy dependencies (`faster_whisper`, `whisper`, subprocess calls to
`whisper-cli`) lazily, inside the methods that need them, so importing `sys2txt` never pays
for a backend you don't use. Engines that load a model (`FasterWhisperEngine`,
`OpenAIWhisperEngine`) extend `_CachedModelEngine`, which keeps one loaded model per engine
instance, keyed on whatever makes it a different model (e.g. `(model, device,
compute_type)`), and reloads only when that key changes.

### Adding a new engine

1. Write a class that implements the `TranscriptionEngine` protocol (or extend
   `_CachedModelEngine` if it loads a model). It should return a `Transcript` with real
   per-utterance `Cue` timings — `config.timestamps` only affects plain-text rendering,
   which happens later in `formats.py`, not in the engine.
2. Add an instance of it to `ENGINES` in `engines.py`, in the position you want it tried in
   `auto` mode.
3. That's it — `ENGINE_NAMES`, the `--engine` CLI choice, and the `auto` fallback all derive
   from `ENGINES`.

## Where to look next

- [Python API](python-api.md) documents the same functions (`transcribe_once`,
  `transcribe_live`, `iter_audio_segments`, etc.) from a library-user's point of view.
- [CLI reference](cli-reference.md) documents every flag `__main__.py` exposes.
- [Engines & devices](engines-and-devices.md) covers choosing and configuring an engine at
  runtime, rather than implementing one.
