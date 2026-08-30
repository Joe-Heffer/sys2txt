"""Tests for sys2txt.transcribe module."""

import unittest
from unittest.mock import MagicMock, patch

from sys2txt.formats import Cue, Transcript
from sys2txt.transcribe import TranscriptionConfig, transcribe_file, transcribe_file_cues


def transcript(*texts, language=None):
    """Build a Transcript with one one-second cue per text."""
    cues = tuple(Cue(start=float(i), end=float(i + 1), text=text) for i, text in enumerate(texts))
    return Transcript(cues=cues, language=language)


def fake_engine(name, result):
    """Build a stand-in engine that returns ``result`` from transcribe()."""
    engine = MagicMock()
    engine.name = name
    engine.transcribe.return_value = result
    return engine


class TestTranscribeFile(unittest.TestCase):
    """Tests for the transcribe_file() function."""

    def test_renders_the_engine_transcript_as_text(self):
        engine = fake_engine("faster", transcript("test transcript"))

        with patch("sys2txt.transcribe.get_engine", return_value=engine) as mock_get_engine:
            result = transcribe_file("/path/to/audio.wav", TranscriptionConfig())

        self.assertEqual(result, "test transcript")
        mock_get_engine.assert_called_once_with("auto")

    def test_timestamps_are_rendered_not_asked_of_the_engine(self):
        """The engine always returns timed cues; --timestamps only affects plain-text rendering."""
        engine = fake_engine("faster", transcript("faster transcript"))
        config = TranscriptionConfig(engine="faster", model="base", language="en", timestamps=True)

        with patch("sys2txt.transcribe.get_engine", return_value=engine):
            result = transcribe_file("/path/to/audio.wav", config)

        self.assertEqual(result, "[  0.00-  1.00] faster transcript")

    def test_the_engine_name_is_lowercased(self):
        engine = fake_engine("whisper", transcript("whisper transcript"))

        with patch("sys2txt.transcribe.get_engine", return_value=engine) as mock_get_engine:
            transcribe_file("/path/to/audio.wav", TranscriptionConfig(engine="Whisper"))

        mock_get_engine.assert_called_once_with("whisper")

    def test_invalid_engine(self):
        """Test transcribe_file() raises ValueError for invalid engine."""
        with self.assertRaises(ValueError) as cm:
            transcribe_file("/path/to/audio.wav", TranscriptionConfig(engine="invalid"))

        self.assertIn("Unknown engine", str(cm.exception))
        self.assertIn("invalid", str(cm.exception))


class TestTranscribeFileCues(unittest.TestCase):
    """Tests for the transcribe_file_cues() function."""

    def test_returns_the_engine_transcript_unchanged(self):
        """Test transcribe_file_cues() hands back the engine's cues and language."""
        engine = fake_engine("faster", transcript("hello", language="en"))

        with patch("sys2txt.transcribe.get_engine", return_value=engine):
            result = transcribe_file_cues("/path/to/audio.wav", TranscriptionConfig(engine="faster"))

        self.assertEqual(result.cues, (Cue(0.0, 1.0, "hello"),))
        self.assertEqual(result.language, "en")

    def test_hands_the_whole_config_to_the_engine(self):
        """The config travels intact rather than being destructured into positional arguments."""
        engine = fake_engine("cpp", transcript("cpp transcript"))
        config = TranscriptionConfig(
            engine="cpp",
            model="small",
            language="en",
            model_path="/path/to/model.bin",
            whisper_cpp_path="/path/to/whisper-cli",
            device="vulkan",
        )

        with patch("sys2txt.transcribe.get_engine", return_value=engine):
            transcribe_file_cues("/path/to/audio.wav", config)

        engine.transcribe.assert_called_once_with("/path/to/audio.wav", config)

    def test_invalid_engine(self):
        """Test transcribe_file_cues() raises ValueError for an invalid engine."""
        with self.assertRaises(ValueError) as cm:
            transcribe_file_cues("/path/to/audio.wav", TranscriptionConfig(engine="invalid"))

        self.assertIn("Unknown engine", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
