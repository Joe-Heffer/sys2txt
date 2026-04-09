"""Tests for sys2txt.transcribe module."""

import os
import unittest
from pathlib import Path
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
        mock_transcribe.assert_called_once_with("/path/to/audio.wav", "small", None, False, "auto")

    @patch("sys2txt.transcribe._transcribe_faster_whisper")
    def test_transcribe_file_faster_engine(self, mock_transcribe):
        """Test transcribe_file() with explicit faster engine."""
        mock_transcribe.return_value = "faster transcript"

        result = transcribe_file("/path/to/audio.wav", "faster", "base", "en", True)

        self.assertEqual(result, "faster transcript")
        mock_transcribe.assert_called_once_with("/path/to/audio.wav", "base", "en", True, "auto")

    @patch("sys2txt.transcribe._transcribe_openai_whisper")
    def test_transcribe_file_whisper_engine(self, mock_transcribe):
        """Test transcribe_file() with explicit whisper engine."""
        mock_transcribe.return_value = "whisper transcript"

        result = transcribe_file("/path/to/audio.wav", "whisper", "medium", "fr", False)

        self.assertEqual(result, "whisper transcript")
        mock_transcribe.assert_called_once_with("/path/to/audio.wav", "medium", "fr", False)

    @patch("sys2txt.transcribe._transcribe_whisper_cpp")
    def test_transcribe_file_cpp_engine(self, mock_transcribe):
        """Test transcribe_file() with cpp engine."""
        mock_transcribe.return_value = "cpp transcript"

        result = transcribe_file(
            "/path/to/audio.wav",
            "cpp",
            "small",
            "en",
            True,
            model_path="/path/to/model.bin",
            whisper_cpp_path="/path/to/whisper-cli",
            device="vulkan",
        )

        self.assertEqual(result, "cpp transcript")
        mock_transcribe.assert_called_once_with(
            "/path/to/audio.wav",
            "small",
            "en",
            True,
            "/path/to/model.bin",
            "/path/to/whisper-cli",
            "vulkan",
        )

    def test_transcribe_file_invalid_engine(self):
        """Test transcribe_file() raises ValueError for invalid engine."""
        with self.assertRaises(ValueError) as cm:
            transcribe_file("/path/to/audio.wav", "invalid", "small", None, False)

        self.assertIn("Unknown engine", str(cm.exception))
        self.assertIn("invalid", str(cm.exception))


class TestTranscribeFasterWhisper(unittest.TestCase):
    """Tests for the _transcribe_faster_whisper() function."""

    def setUp(self):
        """Reset cached model between tests."""
        import sys2txt.transcribe as t

        t._faster_whisper_model = None
        t._faster_whisper_model_key = None

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
    def test_transcribe_faster_whisper_cuda_device_from_env(self, mock_model_class):
        """Test _transcribe_faster_whisper() uses CUDA when env var set with auto device."""
        from sys2txt.transcribe import _transcribe_faster_whisper

        mock_model = mock_model_class.return_value
        mock_model.transcribe.return_value = ([], None)

        _transcribe_faster_whisper("/path/to/audio.wav", "small", None, False, device="auto")

        mock_model_class.assert_called_once_with("small", device="cuda", compute_type="float16")

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_faster_whisper_cuda_device_explicit(self, mock_model_class):
        """Test _transcribe_faster_whisper() uses CUDA when device=cuda."""
        from sys2txt.transcribe import _transcribe_faster_whisper

        mock_model = mock_model_class.return_value
        mock_model.transcribe.return_value = ([], None)

        _transcribe_faster_whisper("/path/to/audio.wav", "small", None, False, device="cuda")

        mock_model_class.assert_called_once_with("small", device="cuda", compute_type="float16")

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_faster_whisper_cpu_device_explicit(self, mock_model_class):
        """Test _transcribe_faster_whisper() uses CPU when device=cpu."""
        from sys2txt.transcribe import _transcribe_faster_whisper

        mock_model = mock_model_class.return_value
        mock_model.transcribe.return_value = ([], None)

        _transcribe_faster_whisper("/path/to/audio.wav", "small", None, False, device="cpu")

        mock_model_class.assert_called_once_with("small", device="cpu", compute_type="int8")

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

    def setUp(self):
        """Reset cached model between tests."""
        import sys2txt.transcribe as t

        t._openai_whisper_model = None
        t._openai_whisper_model_key = None

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


class TestResolveWhisperCppBinary(unittest.TestCase):
    """Tests for the _resolve_whisper_cpp_binary() function."""

    def test_explicit_path_valid(self):
        """Test explicit path that exists."""
        from sys2txt.transcribe import _resolve_whisper_cpp_binary

        with patch("os.path.isfile", return_value=True):
            result = _resolve_whisper_cpp_binary("/path/to/whisper-cli")

        self.assertEqual(result, "/path/to/whisper-cli")

    def test_explicit_path_invalid(self):
        """Test explicit path that doesn't exist."""
        from sys2txt.transcribe import _resolve_whisper_cpp_binary

        with patch("os.path.isfile", return_value=False):
            with self.assertRaises(RuntimeError) as cm:
                _resolve_whisper_cpp_binary("/path/to/whisper-cli")

        self.assertIn("not found at", str(cm.exception))

    @patch.dict(os.environ, {"SYS2TXT_WHISPER_CPP": "/env/whisper-cli"})
    def test_env_var_valid(self):
        """Test environment variable path that exists."""
        from sys2txt.transcribe import _resolve_whisper_cpp_binary

        with patch("os.path.isfile", return_value=True):
            result = _resolve_whisper_cpp_binary(None)

        self.assertEqual(result, "/env/whisper-cli")

    @patch.dict(os.environ, {"SYS2TXT_WHISPER_CPP": "/env/whisper-cli"})
    def test_env_var_invalid(self):
        """Test environment variable path that doesn't exist."""
        from sys2txt.transcribe import _resolve_whisper_cpp_binary

        with patch("os.path.isfile", return_value=False):
            with self.assertRaises(RuntimeError) as cm:
                _resolve_whisper_cpp_binary(None)

        self.assertIn("SYS2TXT_WHISPER_CPP", str(cm.exception))

    @patch.dict(os.environ, {}, clear=True)
    def test_path_lookup_found(self):
        """Test PATH lookup succeeds."""
        from sys2txt.transcribe import _resolve_whisper_cpp_binary

        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            result = _resolve_whisper_cpp_binary(None)

        self.assertEqual(result, "/usr/bin/whisper-cli")

    @patch.dict(os.environ, {}, clear=True)
    def test_path_lookup_not_found(self):
        """Test PATH lookup fails."""
        from sys2txt.transcribe import _resolve_whisper_cpp_binary

        with patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as cm:
                _resolve_whisper_cpp_binary(None)

        self.assertIn("whisper-cli binary not found", str(cm.exception))


class TestResolveWhisperCppModelPath(unittest.TestCase):
    """Tests for the _resolve_whisper_cpp_model_path() function."""

    def test_explicit_path_valid(self):
        """Test explicit model path that exists."""
        from sys2txt.transcribe import _resolve_whisper_cpp_model_path

        with patch("os.path.isfile", return_value=True):
            result = _resolve_whisper_cpp_model_path("/path/to/model.bin", "small")

        self.assertEqual(result, "/path/to/model.bin")

    def test_explicit_path_invalid(self):
        """Test explicit model path that doesn't exist."""
        from sys2txt.transcribe import _resolve_whisper_cpp_model_path

        with patch("os.path.isfile", return_value=False):
            with self.assertRaises(RuntimeError) as cm:
                _resolve_whisper_cpp_model_path("/path/to/model.bin", "small")

        self.assertIn("not found at", str(cm.exception))

    @patch.dict(os.environ, {"SYS2TXT_WHISPER_CPP_MODELS": "/models"})
    def test_env_var_models_dir(self):
        """Test models directory from environment variable."""
        from sys2txt.transcribe import _resolve_whisper_cpp_model_path

        with patch("os.path.isfile", return_value=True):
            result = _resolve_whisper_cpp_model_path(None, "small")

        self.assertEqual(result, "/models/ggml-small.bin")

    @patch.dict(os.environ, {}, clear=True)
    def test_default_path(self):
        """Test default path in ~/.local/share/whisper.cpp/models/."""
        from sys2txt.transcribe import _resolve_whisper_cpp_model_path

        expected_path = Path.home() / ".local" / "share" / "whisper.cpp" / "models" / "ggml-tiny.bin"

        with patch.object(Path, "is_file", return_value=True):
            result = _resolve_whisper_cpp_model_path(None, "tiny")

        self.assertEqual(result, str(expected_path))

    @patch.dict(os.environ, {}, clear=True)
    def test_model_not_found(self):
        """Test model not found anywhere."""
        from sys2txt.transcribe import _resolve_whisper_cpp_model_path

        with patch("os.path.isfile", return_value=False):
            with patch.object(Path, "is_file", return_value=False):
                with self.assertRaises(RuntimeError) as cm:
                    _resolve_whisper_cpp_model_path(None, "small")

        self.assertIn("ggml-small.bin", str(cm.exception))


class TestParseWhisperCppOutput(unittest.TestCase):
    """Tests for the _parse_whisper_cpp_output() function."""

    def test_parse_with_timestamps(self):
        """Test parsing whisper.cpp output with timestamps enabled."""
        from sys2txt.transcribe import _parse_whisper_cpp_output

        output = """[00:00:00.000 --> 00:00:05.120]   Hello world
[00:00:05.120 --> 00:00:10.240]   This is a test"""

        result = _parse_whisper_cpp_output(output, timestamps=True)

        self.assertIn("[  0.00-  5.12] Hello world", result)
        self.assertIn("[  5.12- 10.24] This is a test", result)

    def test_parse_without_timestamps(self):
        """Test parsing whisper.cpp output without timestamps."""
        from sys2txt.transcribe import _parse_whisper_cpp_output

        output = """[00:00:00.000 --> 00:00:05.120]   Hello world
[00:00:05.120 --> 00:00:10.240]   This is a test"""

        result = _parse_whisper_cpp_output(output, timestamps=False)

        self.assertEqual(result, "Hello world This is a test")

    def test_parse_empty_segments_ignored(self):
        """Test that empty segments are ignored."""
        from sys2txt.transcribe import _parse_whisper_cpp_output

        output = """[00:00:00.000 --> 00:00:05.120]   Hello
[00:00:05.120 --> 00:00:10.240]
[00:00:10.240 --> 00:00:15.000]   World"""

        result = _parse_whisper_cpp_output(output, timestamps=False)

        self.assertEqual(result, "Hello World")

    def test_parse_non_matching_lines_ignored(self):
        """Test that non-matching lines are ignored."""
        from sys2txt.transcribe import _parse_whisper_cpp_output

        output = """whisper_init_from_file_no_state: loading model...
[00:00:00.000 --> 00:00:05.120]   Hello world
main: some debug output"""

        result = _parse_whisper_cpp_output(output, timestamps=False)

        self.assertEqual(result, "Hello world")


class TestTimestampToSeconds(unittest.TestCase):
    """Tests for the _timestamp_to_seconds() function."""

    def test_simple_seconds(self):
        """Test simple seconds conversion."""
        from sys2txt.transcribe import _timestamp_to_seconds

        result = _timestamp_to_seconds("00:00:05.120")
        self.assertAlmostEqual(result, 5.12, places=3)

    def test_minutes_and_seconds(self):
        """Test minutes and seconds conversion."""
        from sys2txt.transcribe import _timestamp_to_seconds

        result = _timestamp_to_seconds("00:02:30.500")
        self.assertAlmostEqual(result, 150.5, places=3)

    def test_hours_minutes_seconds(self):
        """Test hours, minutes, and seconds conversion."""
        from sys2txt.transcribe import _timestamp_to_seconds

        result = _timestamp_to_seconds("01:30:45.750")
        self.assertAlmostEqual(result, 5445.75, places=3)


class TestTranscribeWhisperCpp(unittest.TestCase):
    """Tests for the _transcribe_whisper_cpp() function."""

    @patch("sys2txt.transcribe._resolve_whisper_cpp_binary")
    @patch("sys2txt.transcribe._resolve_whisper_cpp_model_path")
    @patch("subprocess.run")
    def test_transcribe_success(self, mock_run, mock_model_path, mock_binary):
        """Test successful transcription."""
        from sys2txt.transcribe import _transcribe_whisper_cpp

        mock_binary.return_value = "/path/to/whisper-cli"
        mock_model_path.return_value = "/path/to/model.bin"
        mock_run.return_value = MagicMock(
            stdout="[00:00:00.000 --> 00:00:05.000]   Hello world\n",
            returncode=0,
        )

        result = _transcribe_whisper_cpp("/path/to/audio.wav", "small", None, False, None, None, "auto")

        self.assertEqual(result, "Hello world")
        mock_run.assert_called_once()

    @patch("sys2txt.transcribe._resolve_whisper_cpp_binary")
    @patch("sys2txt.transcribe._resolve_whisper_cpp_model_path")
    @patch("subprocess.run")
    def test_transcribe_with_language(self, mock_run, mock_model_path, mock_binary):
        """Test transcription with language specified."""
        from sys2txt.transcribe import _transcribe_whisper_cpp

        mock_binary.return_value = "/path/to/whisper-cli"
        mock_model_path.return_value = "/path/to/model.bin"
        mock_run.return_value = MagicMock(
            stdout="[00:00:00.000 --> 00:00:05.000]   Bonjour\n",
            returncode=0,
        )

        _transcribe_whisper_cpp("/path/to/audio.wav", "small", "fr", False, None, None, "auto")

        # Check -l fr is in the command
        call_args = mock_run.call_args[0][0]
        self.assertIn("-l", call_args)
        self.assertIn("fr", call_args)

    @patch("sys2txt.transcribe._resolve_whisper_cpp_binary")
    @patch("sys2txt.transcribe._resolve_whisper_cpp_model_path")
    @patch("subprocess.run")
    def test_transcribe_cpu_device(self, mock_run, mock_model_path, mock_binary):
        """Test transcription with CPU device adds --no-gpu flag."""
        from sys2txt.transcribe import _transcribe_whisper_cpp

        mock_binary.return_value = "/path/to/whisper-cli"
        mock_model_path.return_value = "/path/to/model.bin"
        mock_run.return_value = MagicMock(
            stdout="[00:00:00.000 --> 00:00:05.000]   Hello\n",
            returncode=0,
        )

        _transcribe_whisper_cpp("/path/to/audio.wav", "small", None, False, None, None, "cpu")

        call_args = mock_run.call_args[0][0]
        self.assertIn("--no-gpu", call_args)

    @patch("sys2txt.transcribe._resolve_whisper_cpp_binary")
    @patch("sys2txt.transcribe._resolve_whisper_cpp_model_path")
    @patch("subprocess.run")
    def test_transcribe_vulkan_device(self, mock_run, mock_model_path, mock_binary):
        """Test transcription with Vulkan device does not add --no-gpu."""
        from sys2txt.transcribe import _transcribe_whisper_cpp

        mock_binary.return_value = "/path/to/whisper-cli"
        mock_model_path.return_value = "/path/to/model.bin"
        mock_run.return_value = MagicMock(
            stdout="[00:00:00.000 --> 00:00:05.000]   Hello\n",
            returncode=0,
        )

        _transcribe_whisper_cpp("/path/to/audio.wav", "small", None, False, None, None, "vulkan")

        call_args = mock_run.call_args[0][0]
        self.assertNotIn("--no-gpu", call_args)

    @patch("sys2txt.transcribe._resolve_whisper_cpp_binary")
    @patch("sys2txt.transcribe._resolve_whisper_cpp_model_path")
    @patch("subprocess.run")
    def test_transcribe_failure(self, mock_run, mock_model_path, mock_binary):
        """Test transcription failure raises RuntimeError."""
        import subprocess

        from sys2txt.transcribe import _transcribe_whisper_cpp

        mock_binary.return_value = "/path/to/whisper-cli"
        mock_model_path.return_value = "/path/to/model.bin"
        mock_run.side_effect = subprocess.CalledProcessError(1, "whisper-cli", stderr="Error: model not found")

        with self.assertRaises(RuntimeError) as cm:
            _transcribe_whisper_cpp("/path/to/audio.wav", "small", None, False, None, None, "auto")

        self.assertIn("whisper-cli failed", str(cm.exception))

    @patch("sys2txt.transcribe._resolve_whisper_cpp_binary")
    @patch("sys2txt.transcribe._resolve_whisper_cpp_model_path")
    @patch("subprocess.run")
    def test_transcribe_timeout_raises_runtime_error(self, mock_run, mock_model_path, mock_binary):
        """Test that a hung whisper-cli process raises RuntimeError after timeout."""
        import subprocess

        from sys2txt.transcribe import _transcribe_whisper_cpp

        mock_binary.return_value = "/path/to/whisper-cli"
        mock_model_path.return_value = "/path/to/model.bin"
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="whisper-cli", timeout=300)

        with self.assertRaises(RuntimeError) as cm:
            _transcribe_whisper_cpp("/path/to/audio.wav", "small", None, False, None, None, "auto")

        self.assertIn("timed out", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
