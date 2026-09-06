"""End-to-end tests that exercise real ffmpeg (and, when available, real PulseAudio).

Every other test module mocks ffmpeg and PulseAudio entirely, so nothing in the suite has
ever caught an ffmpeg argument-shape mismatch or a real subprocess timing bug -- despite CI
installing both packages. These tests spend that installation: they run the real `ffmpeg`
binary and assert on the files/output it actually produces, rather than on mock call shapes.

The transcription engine itself is mocked (downloading a real Whisper model in CI would be
slow and network-dependent, exactly the kind of flake risk this suite is trying to remove
elsewhere) -- these tests are about the audio and CLI plumbing around it.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from sys2txt.audio import record_once
from sys2txt.formats import Cue, Transcript
from sys2txt.pulse import get_default_monitor_source

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None


def _make_fixture_wav(path: str, duration: float = 0.5) -> None:
    """Generate a short real WAV file with real ffmpeg (a synthetic tone, no audio device needed)."""
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration}",
            "-ac",
            "1",
            "-ar",
            "16000",
            path,
            "-y",
        ],
        check=True,
    )


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg is not installed")
class TestRealFfmpegFixture(unittest.TestCase):
    """Sanity-checks the fixture generator itself produces a real, valid WAV file."""

    def test_fixture_is_a_real_wav_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "fixture.wav")
            _make_fixture_wav(path)

            self.assertTrue(os.path.isfile(path))
            with open(path, "rb") as f:
                header = f.read(12)
            self.assertEqual(header[:4], b"RIFF")
            self.assertEqual(header[8:12], b"WAVE")
            self.assertGreater(os.path.getsize(path), 1024)


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg is not installed")
class TestCliOverARealWavFile(unittest.TestCase):
    """Runs the real `sys2txt once --input` CLI path over a real WAV file.

    Only the transcription engine is mocked; argument parsing, option validation, transcript
    rendering and file writing all run for real.
    """

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        self.wav_path = os.path.join(self.tmpdir.name, "fixture.wav")
        _make_fixture_wav(self.wav_path)
        self.output_path = os.path.join(self.tmpdir.name, "out.txt")

    @patch("sys2txt.__main__.transcribe_file_cues")
    def test_transcribes_a_real_wav_file_and_writes_the_output(self, mock_transcribe):
        mock_transcribe.return_value = Transcript(cues=(Cue(0.0, 0.5, "test tone"),))

        argv = [
            "sys2txt",
            "once",
            "--input",
            self.wav_path,
            "--output",
            self.output_path,
        ]
        with patch.object(sys, "argv", argv):
            from sys2txt.__main__ import main

            main()

        mock_transcribe.assert_called_once()
        self.assertEqual(mock_transcribe.call_args[0][0], self.wav_path)
        with open(self.output_path) as f:
            content = f.read()
        self.assertIn("test tone", content)

    @patch("sys2txt.__main__.transcribe_file_cues")
    def test_json_format_produces_valid_json_over_a_real_wav_file(self, mock_transcribe):
        mock_transcribe.return_value = Transcript(cues=(Cue(0.0, 0.5, "test tone"),), language="en")

        argv = [
            "sys2txt",
            "once",
            "--input",
            self.wav_path,
            "--format",
            "json",
            "--output",
            self.output_path,
        ]
        with patch.object(sys, "argv", argv):
            from sys2txt.__main__ import main

            main()

        with open(self.output_path) as f:
            document = json.load(f)
        self.assertEqual(document["language"], "en")
        self.assertEqual(document["segments"][0]["text"], "test tone")


def _real_pulse_default_source():
    """The default monitor source, or None if PulseAudio isn't actually reachable here."""
    try:
        return get_default_monitor_source()
    except Exception:
        return None


@unittest.skipUnless(FFMPEG_AVAILABLE, "ffmpeg is not installed")
@unittest.skipUnless(_real_pulse_default_source(), "no reachable PulseAudio/PipeWire source")
class TestRealPulseRecording(unittest.TestCase):
    """A true end-to-end smoke test: real ffmpeg capturing from a real PulseAudio source.

    Skips itself on any machine without a reachable PulseAudio/PipeWire server (most CI
    runners), rather than failing -- it runs for real wherever audio is actually available.
    """

    def test_record_once_produces_a_real_wav_file(self):
        source = _real_pulse_default_source()
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "capture.wav")

            record_once(source, path, duration=1)

            self.assertTrue(os.path.isfile(path))
            with open(path, "rb") as f:
                header = f.read(12)
            self.assertEqual(header[:4], b"RIFF")
            self.assertEqual(header[8:12], b"WAVE")


if __name__ == "__main__":
    unittest.main()
