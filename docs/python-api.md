# Use as a Python library

`sys2txt` is importable as well as runnable. The library records and transcribes; printing, saving
and when to stop are yours.

Transcribe a fixed recording:

```python
from sys2txt import TranscriptionConfig, get_default_monitor_source, transcribe_once

config = TranscriptionConfig(model="small.en")
text = transcribe_once(get_default_monitor_source(), config, duration=30)
```

Consume a live recording segment by segment. `transcribe_live()` is a generator: it records until you
stop iterating, and breaking out of the loop shuts ffmpeg down and cleans up its temporary files.

```python
from sys2txt import TranscriptionConfig, get_default_monitor_source, transcribe_live

config = TranscriptionConfig(model="small.en")
for segment in transcribe_live(get_default_monitor_source(), config, segment_seconds=8):
    print(f"[{segment.start:.0f}s] {segment.text}")
    if "goodbye" in segment.text.lower():
        break
```

A segment whose transcription fails or times out is yielded with empty `text`, an `error` describing
the failure (`segment.failed` is `True`) and a warning in the log, so a failure never stops the stream
and is never mistaken for silence. A segment that times out does not hold up the ones after it: its
worker is abandoned and the next segment is transcribed on a fresh one.

Each segment also reports how far behind recording it is. `segment.lag` is the seconds of audio still
waiting to be transcribed — zero while you keep up — and `segment.dropped` counts segments discarded
just before it. Pass `max_lag=` to cap the backlog by dropping the oldest audio:

```python
for segment in transcribe_live(source, config, segment_seconds=8, max_lag=30):
    if segment.dropped:
        print(f"... {segment.dropped} segment(s) of audio dropped ...")
```

To handle the audio yourself, `iter_audio_segments()` yields `AudioSegment(index, path, lag, dropped)`
values without transcribing them, and `transcribe_file(path, config)` transcribes any audio file. A
segment's file is removed as soon as you ask for the next one, so copy it if you need it later. Nothing
in the library prints or writes files, and every module logs through the standard `logging` module under
the `sys2txt` logger.

For timed output, use the `_cues` variants and render them yourself. They return a `Transcript` of
`Cue(start, end, text)` values plus the detected language, which `render_transcript()` turns into any
of the output formats:

```python
from sys2txt import TranscriptionConfig, render_transcript, transcribe_file_cues

transcript = transcribe_file_cues("talk.wav", TranscriptionConfig(model="small.en"))
with open("talk.srt", "w", encoding="utf-8") as f:
    f.write(render_transcript(transcript.cues, "srt"))
```

In live mode the same cues are on each `TranscriptSegment` as `segment.cues`, already rebased onto the
timeline of the recording.

The full public API is `AudioSegment`, `Cue`, `OUTPUT_FORMATS`, `Transcript`, `TranscriptSegment`,
`TranscriptionConfig`, `get_default_monitor_source`, `iter_audio_segments`, `list_pulse_sources`,
`record_once`, `render_transcript`, `transcribe_file`, `transcribe_file_cues`, `transcribe_live`,
`transcribe_once` and `transcribe_once_cues`. The package ships type hints (`py.typed`).
