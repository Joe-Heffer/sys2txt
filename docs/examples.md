# Examples

Record 30s of system audio from the default monitor and transcribe:

```bash
sys2txt once --duration 30 --model small --output transcript.txt
```

Use a specific PulseAudio source:

```bash
sys2txt once --source alsa_output.usb-Focusrite_Scarlett.monitor --model base
```

Live mode with shorter latency and timestamps:

```bash
sys2txt live --segment-seconds 5 --timestamps
```

Produce subtitles for a recording, ready to drop next to a video:

```bash
sys2txt once --input talk.wav --format srt --output talk.srt
sys2txt once --input talk.wav --format vtt --output talk.vtt
```

Keep a slow model close to live, dropping audio rather than falling more than a minute behind:

```bash
sys2txt live --model medium --segment-seconds 5 --max-lag 60
```

Capture a meeting live as WebVTT, stopping after 30 seconds of silence:

```bash
sys2txt live --format vtt --silence-timeout 30 --output meeting.vtt
```

Get machine-readable output with per-segment timings:

```bash
sys2txt once --input talk.wav --format json --output talk.json
```

Force the reference openai-whisper engine:

```bash
sys2txt once --engine whisper --model base
```

Transcribe an existing audio file:

```bash
sys2txt once --input recording.wav --model small
```

## Just want one-liners (no sys2txt)?

Find the default sink and its monitor source:

```bash
pactl get-default-sink
pactl list short sources | grep monitor
```

Record 30s of system audio from the default monitor to a WAV at 16 kHz mono (good for Whisper):

```bash
ffmpeg -hide_banner -loglevel error -f pulse -i "$(pactl get-default-sink).monitor" -ac 1 -ar 16000 -t 30 out.wav
```

Transcribe with openai-whisper CLI:

```bash
whisper out.wav --model small --task transcribe --language en
```
