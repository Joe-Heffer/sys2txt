"""Tests for sys2txt.transcribe module."""

import os
import unittest
from unittest.mock import MagicMock, patch

from sys2txt.transcribe import transcribe_file


class TestTranscribeFile(unittest.TestCase):
    """Tests for the transcribe_file() function."""

    def test_transcribe_file_auto_selects_faster_whisper(self):
        """Test transcribe_file() auto-selects faster-whisper when available."""
        # Mock faster_whisper import being successful
        with patch("sys2txt.transcribe._transcribe_faster_whisper") as mock_transcribe:
            mock_transcribe.return_value = "test transcript"
            # The actual import will succeed since faster_whisper is installed
            result = transcribe_file("/path/to/audio.wav", "auto", "small", None, False)

        self.assertEqual(result, "test transcript")
        mock_transcribe.assert_called_once_with("/path/to/audio.wav", "small", None, False)

    @patch("sys2txt.transcribe._transcribe_faster_whisper")
    def test_transcribe_file_faster_engine(self, mock_transcribe):
        """Test transcribe_file() with explicit faster engine."""
        mock_transcribe.return_value = "faster transcript"

        result = transcribe_file("/path/to/audio.wav", "faster", "base", "en", True)

        self.assertEqual(result, "faster transcript")
        mock_transcribe.assert_called_once_with("/path/to/audio.wav", "base", "en", True)

    @patch("sys2txt.transcribe._transcribe_openai_whisper")
    def test_transcribe_file_whisper_engine(self, mock_transcribe):
        """Test transcribe_file() with explicit whisper engine."""
        mock_transcribe.return_value = "whisper transcript"

        result = transcribe_file("/path/to/audio.wav", "whisper", "medium", "fr", False)

        self.assertEqual(result, "whisper transcript")
        mock_transcribe.assert_called_once_with("/path/to/audio.wav", "medium", "fr", False)

    def test_transcribe_file_invalid_engine(self):
        """Test transcribe_file() raises ValueError for invalid engine."""
        with self.assertRaises(ValueError) as cm:
            transcribe_file("/path/to/audio.wav", "invalid", "small", None, False)

        self.assertIn("Unknown engine", str(cm.exception))
        self.assertIn("invalid", str(cm.exception))


class TestTranscribeFasterWhisper(unittest.TestCase):
    """Tests for the _transcribe_faster_whisper() function."""

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_faster_whisper_no_timestamps(self, mock_model_class):
        """Test _transcribe_faster_whisper() without timestamps."""
        from sys2txt.transcribe import _transcribe_faster_whisper

        # Mock segment objects
        seg1 = MagicMock()
        seg1.text = " Hello world "
        seg1.start = 0.0
        seg1.end = 1.5

        seg2 = MagicMock()
        seg2.text = " Test audio "
        seg2.start = 1.5
        seg2.end = 3.0

        mock_model = mock_model_class.return_value
        mock_model.transcribe.return_value = ([seg1, seg2], None)

        result = _transcribe_faster_whisper("/path/to/audio.wav", "small", None, False)

        self.assertEqual(result, "Hello world Test audio")
        mock_model.transcribe.assert_called_once_with("/path/to/audio.wav", vad_filter=True, language=None)

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_faster_whisper_with_timestamps(self, mock_model_class):
        """Test _transcribe_faster_whisper() with timestamps."""
        from sys2txt.transcribe import _transcribe_faster_whisper

        # Mock segment objects
        seg1 = MagicMock()
        seg1.text = " Hello "
        seg1.start = 0.0
        seg1.end = 1.5

        seg2 = MagicMock()
        seg2.text = " world "
        seg2.start = 1.5
        seg2.end = 3.0

        mock_model = mock_model_class.return_value
        mock_model.transcribe.return_value = ([seg1, seg2], None)

        result = _transcribe_faster_whisper("/path/to/audio.wav", "base", "en", True)

        self.assertIn("[  0.00-  1.50] Hello", result)
        self.assertIn("[  1.50-  3.00] world", result)
        mock_model.transcribe.assert_called_once_with("/path/to/audio.wav", vad_filter=True, language="en")

    @patch("faster_whisper.WhisperModel")
    @patch.dict(os.environ, {"SYS2TXT_DEVICE": "cuda"})
    def test_transcribe_faster_whisper_cuda_device(self, mock_model_class):
        """Test _transcribe_faster_whisper() uses CUDA when env var set."""
        from sys2txt.transcribe import _transcribe_faster_whisper

        mock_model = mock_model_class.return_value
        mock_model.transcribe.return_value = ([], None)

        _transcribe_faster_whisper("/path/to/audio.wav", "small", None, False)

        mock_model_class.assert_called_once_with("small", device="cuda", compute_type="float16")

    def test_transcribe_faster_whisper_not_installed(self):
        """Test _transcribe_faster_whisper() raises RuntimeError when not installed."""
        from sys2txt.transcribe import _transcribe_faster_whisper

        # Mock the import to fail at the point where it's actually imported in the function
        with patch.dict("sys.modules", {"faster_whisper": None}):
            with self.assertRaises(RuntimeError) as cm:
                _transcribe_faster_whisper("/path/to/audio.wav", "small", None, False)

            self.assertIn("faster-whisper is not installed", str(cm.exception))


class TestTranscribeOpenAIWhisper(unittest.TestCase):
    """Tests for the _transcribe_openai_whisper() function."""

    @patch("whisper.load_model")
    def test_transcribe_openai_whisper_no_timestamps(self, mock_load_model):
        """Test _transcribe_openai_whisper() without timestamps."""
        from sys2txt.transcribe import _transcribe_openai_whisper

        mock_model = MagicMock()
        mock_load_model.return_value = mock_model
        mock_model.transcribe.return_value = {"text": " Hello world "}

        result = _transcribe_openai_whisper("/path/to/audio.wav", "small", None, False)

        self.assertEqual(result, "Hello world")
        mock_load_model.assert_called_once_with("small")
        mock_model.transcribe.assert_called_once_with("/path/to/audio.wav", language=None)

    @patch("whisper.load_model")
    def test_transcribe_openai_whisper_with_timestamps(self, mock_load_model):
        """Test _transcribe_openai_whisper() with timestamps."""
        from sys2txt.transcribe import _transcribe_openai_whisper

        mock_model = MagicMock()
        mock_load_model.return_value = mock_model
        mock_model.transcribe.return_value = {
            "text": "Hello world",
            "segments": [
                {"start": 0.0, "end": 1.5, "text": " Hello "},
                {"start": 1.5, "end": 3.0, "text": " world "},
            ],
        }

        result = _transcribe_openai_whisper("/path/to/audio.wav", "base", "en", True)

        self.assertIn("[  0.00-  1.50] Hello", result)
        self.assertIn("[  1.50-  3.00] world", result)
        mock_model.transcribe.assert_called_once_with("/path/to/audio.wav", language="en")

    def test_transcribe_openai_whisper_not_installed(self):
        """Test _transcribe_openai_whisper() raises RuntimeError when not installed."""
        from sys2txt.transcribe import _transcribe_openai_whisper

        # Mock the import to fail at the point where it's actually imported in the function
        with patch.dict("sys.modules", {"whisper": None}):
            with self.assertRaises(RuntimeError) as cm:
                _transcribe_openai_whisper("/path/to/audio.wav", "small", None, False)

            self.assertIn("openai-whisper is not installed", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
