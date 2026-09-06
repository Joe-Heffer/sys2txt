# Live mode

## Keeping up with real time

Recording never waits for transcription. ffmpeg finalizes a segment every `--segment-seconds` whatever
the transcriber is doing, so a model that takes longer than that per segment — a large model on CPU, a
busy machine, or a short `--segment-seconds` chosen for latency — falls further behind every segment,
and "live" output quietly stops being live.

Live mode measures that backlog and warns once it is more than a couple of segments deep:

```
WARNING: Transcription is not keeping up: 32s of audio (4 segments) waiting to be transcribed
```

By default nothing is discarded: the backlog is transcribed in full, just late. To bound it, set a
tolerance and a policy:

```bash
# stay close to live, discarding the oldest audio when more than 30s is queued
sys2txt live --model medium --segment-seconds 5 --max-lag 30

# or refuse to run behind: save what was transcribed and exit non-zero
sys2txt live --model medium --segment-seconds 5 --max-lag 30 --on-lag fail
```

`drop` keeps the newest audio, so the transcript has a hole where the dropped segments were. Timestamps
stay true to the recording, so a gap in them is exactly that hole. Dropped audio is never counted as
silence by `--silence-timeout`, since nobody transcribed it.

Segment files are removed as soon as they have been transcribed, so the temporary directory holds the
backlog rather than the whole session either way.
