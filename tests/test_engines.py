"""Tests for sys2txt.engines module."""

import os
import subprocess
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sys2txt.engines import (
    ENGINE_NAMES,
    ENGINES,
    FasterWhisperEngine,
    OpenAIWhisperEngine,
    TranscriptionConfig,
    TranscriptionEngine,
    WhisperCppEngine,
    _parse_whisper_cpp_output,
    _resolve_device,
    _resolve_whisper_cpp_binary,
    _resolve_whisper_cpp_model_path,
    _timestamp_to_seconds,
    get_engine,
    unload_engines,
)
from sys2txt.formats import Cue


def whisper_segment(text, start, end):
    """Build a mock faster-whisper segment."""
    segment = MagicMock()
    segment.text = text
    segment.start = start
    segment.end = end
    return segment


class TestRegistry(unittest.TestCase):
    """Tests for the engine registry and get_engine()."""

    def test_every_registered_engine_satisfies_the_protocol(self):
        for engine in ENGINES:
            with self.subTest(engine=engine.name):
                self.assertIsInstance(engine, TranscriptionEngine)

    def test_engine_names_start_with_auto_and_cover_the_registry(self):
        self.assertEqual(ENGINE_NAMES, ("auto", "faster", "whisper", "cpp"))

    def test_get_engine_by_name(self):
        expected_types = {
            "faster": FasterWhisperEngine,
            "whisper": OpenAIWhisperEngine,
            "cpp": WhisperCppEngine,
        }
        for name, expected in expected_types.items():
            with self.subTest(name=name):
                self.assertIsInstance(get_engine(name), expected)

    def test_get_engine_by_name_skips_the_availability_check(self):
        """An explicitly named engine runs even when nothing is installed."""
        with patch.dict("sys.modules", {"faster_whisper": None}):
            self.assertEqual(get_engine("faster").name, "faster")

    def test_get_engine_unknown(self):
        with self.assertRaises(ValueError) as cm:
            get_engine("bogus")

        self.assertIn("Unknown engine", str(cm.exception))
        self.assertIn("bogus", str(cm.exception))

    def test_auto_prefers_faster_whisper(self):
        with patch.dict("sys.modules", {"faster_whisper": MagicMock()}):
            self.assertEqual(get_engine("auto").name, "faster")

    def test_auto_falls_back_to_openai_whisper(self):
        with patch.dict("sys.modules", {"faster_whisper": None, "whisper": MagicMock()}):
            self.assertEqual(get_engine("auto").name, "whisper")

    @patch.dict(os.environ, {}, clear=True)
    def test_auto_falls_back_to_whisper_cpp(self):
        with patch.dict("sys.modules", {"faster_whisper": None, "whisper": None}):
            with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
                self.assertEqual(get_engine("auto").name, "cpp")

    @patch.dict(os.environ, {}, clear=True)
    def test_auto_with_nothing_installed_names_every_engine(self):
        """Regression for #63: auto used to fall through to cpp and report a missing binary."""
        with patch.dict("sys.modules", {"faster_whisper": None, "whisper": None}):
            with patch("shutil.which", return_value=None):
                with self.assertRaises(RuntimeError) as cm:
                    get_engine("auto")

        message = str(cm.exception)
        self.assertIn("No transcription engine is installed", message)
        for name in ("faster", "whisper", "cpp"):
            self.assertIn(name, message)

    def test_unload_engines_releases_every_cached_model(self):
        engine = get_engine("faster")
        engine._model = object()
        engine._key = ("small", "cpu", "int8")

        unload_engines()

        self.assertIsNone(engine._model)
        self.assertIsNone(engine._key)


class TestResolveDevice(unittest.TestCase):
    """Tests for the _resolve_device() helper."""

    @patch.dict(os.environ, {}, clear=True)
    def test_auto_defaults_to_cpu(self):
        self.assertEqual(_resolve_device("auto"), "cpu")

    @patch.dict(os.environ, {"SYS2TXT_DEVICE": "cuda"})
    def test_auto_reads_the_environment(self):
        self.assertEqual(_resolve_device("auto"), "cuda")

    @patch.dict(os.environ, {"SYS2TXT_DEVICE": "cuda"})
    def test_explicit_device_beats_the_environment(self):
        self.assertEqual(_resolve_device("cpu"), "cpu")

    def test_gpu_choices_only_whisper_cpp_understands_fall_back_to_cpu(self):
        for device in ("vulkan", "gpu"):
            with self.subTest(device=device):
                self.assertEqual(_resolve_device(device), "cpu")


class TestFasterWhisperEngine(unittest.TestCase):
    """Tests for FasterWhisperEngine."""

    def setUp(self):
        self.engine = FasterWhisperEngine()
        if "faster_whisper" not in sys.modules:
            patcher = patch.dict("sys.modules", {"faster_whisper": MagicMock()})
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_is_available(self):
        with patch.dict("sys.modules", {"faster_whisper": MagicMock()}):
            self.assertTrue(self.engine.is_available())

    def test_is_not_available_when_not_installed(self):
        with patch.dict("sys.modules", {"faster_whisper": None}):
            self.assertFalse(self.engine.is_available())

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_keeps_cue_times(self, mock_model_class):
        mock_model_class.return_value.transcribe.return_value = (
            [whisper_segment(" Hello world ", 0.0, 1.5), whisper_segment(" Test audio ", 1.5, 3.0)],
            None,
        )

        result = self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig())

        self.assertEqual(result.cues, (Cue(0.0, 1.5, "Hello world"), Cue(1.5, 3.0, "Test audio")))
        mock_model_class.return_value.transcribe.assert_called_once_with(
            "/path/to/audio.wav", vad_filter=True, language=None
        )

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_passes_the_language_through(self, mock_model_class):
        mock_model_class.return_value.transcribe.return_value = ([whisper_segment(" Hello ", 0.0, 1.5)], None)

        result = self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(model="base", language="en"))

        self.assertEqual(result.cues, (Cue(0.0, 1.5, "Hello"),))
        self.assertEqual(result.language, "en")
        mock_model_class.return_value.transcribe.assert_called_once_with(
            "/path/to/audio.wav", vad_filter=True, language="en"
        )

    @patch("faster_whisper.WhisperModel")
    @patch.dict(os.environ, {"SYS2TXT_DEVICE": "cuda"})
    def test_cuda_device_from_env(self, mock_model_class):
        mock_model_class.return_value.transcribe.return_value = ([], None)

        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(device="auto"))

        mock_model_class.assert_called_once_with("small", device="cuda", compute_type="float16")

    @patch("faster_whisper.WhisperModel")
    def test_cuda_device_explicit(self, mock_model_class):
        mock_model_class.return_value.transcribe.return_value = ([], None)

        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(device="cuda"))

        mock_model_class.assert_called_once_with("small", device="cuda", compute_type="float16")

    @patch("faster_whisper.WhisperModel")
    def test_cpu_device_explicit(self, mock_model_class):
        mock_model_class.return_value.transcribe.return_value = ([], None)

        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(device="cpu"))

        mock_model_class.assert_called_once_with("small", device="cpu", compute_type="int8")

    def test_transcribe_when_not_installed(self):
        with patch.dict("sys.modules", {"faster_whisper": None}):
            with self.assertRaises(RuntimeError) as cm:
                self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig())

        self.assertIn("faster-whisper is not installed", str(cm.exception))


class TestOpenAIWhisperEngine(unittest.TestCase):
    """Tests for OpenAIWhisperEngine."""

    def setUp(self):
        self.engine = OpenAIWhisperEngine()
        if "whisper" not in sys.modules:
            patcher = patch.dict("sys.modules", {"whisper": MagicMock()})
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_is_available(self):
        with patch.dict("sys.modules", {"whisper": MagicMock()}):
            self.assertTrue(self.engine.is_available())

    def test_is_not_available_when_not_installed(self):
        with patch.dict("sys.modules", {"whisper": None}):
            self.assertFalse(self.engine.is_available())

    @patch("whisper.load_model")
    @patch.dict(os.environ, {}, clear=True)
    def test_untimed_result_becomes_one_cue(self, mock_load_model):
        mock_load_model.return_value.transcribe.return_value = {"text": " Hello world "}

        result = self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig())

        self.assertEqual(result.cues, (Cue(0.0, 0.0, "Hello world"),))
        mock_load_model.assert_called_once_with("small", device="cpu")
        mock_load_model.return_value.transcribe.assert_called_once_with("/path/to/audio.wav", language=None)

    @patch("whisper.load_model")
    def test_segments_keep_their_times(self, mock_load_model):
        mock_load_model.return_value.transcribe.return_value = {
            "text": "Hello world",
            "segments": [
                {"start": 0.0, "end": 1.5, "text": " Hello "},
                {"start": 1.5, "end": 3.0, "text": " world "},
            ],
        }

        result = self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(model="base", language="en"))

        self.assertEqual(result.cues, (Cue(0.0, 1.5, "Hello"), Cue(1.5, 3.0, "world")))
        self.assertEqual(result.language, "en")
        mock_load_model.return_value.transcribe.assert_called_once_with("/path/to/audio.wav", language="en")

    @patch("whisper.load_model")
    def test_device_reaches_load_model(self, mock_load_model):
        mock_load_model.return_value.transcribe.return_value = {"text": ""}

        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(device="cuda"))

        mock_load_model.assert_called_once_with("small", device="cuda")

    @patch("whisper.load_model")
    def test_device_is_part_of_the_cache_key(self, mock_load_model):
        """Regression for #63: the cache key used to ignore the device."""
        mock_load_model.return_value.transcribe.return_value = {"text": ""}

        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(device="cpu"))
        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(device="cuda"))

        self.assertEqual(
            [call.kwargs["device"] for call in mock_load_model.call_args_list],
            ["cpu", "cuda"],
        )

    def test_transcribe_when_not_installed(self):
        with patch.dict("sys.modules", {"whisper": None}):
            with self.assertRaises(RuntimeError) as cm:
                self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig())

        self.assertIn("openai-whisper is not installed", str(cm.exception))


class TestModelCache(unittest.TestCase):
    """Tests for the per-engine model cache."""

    def setUp(self):
        self.engine = FasterWhisperEngine()
        if "faster_whisper" not in sys.modules:
            patcher = patch.dict("sys.modules", {"faster_whisper": MagicMock()})
            patcher.start()
            self.addCleanup(patcher.stop)

    @patch("faster_whisper.WhisperModel")
    def test_same_config_loads_the_model_once(self, mock_model_class):
        mock_model_class.return_value.transcribe.return_value = ([], None)
        config = TranscriptionConfig(device="cpu")

        self.engine.transcribe("/path/to/audio.wav", config)
        self.engine.transcribe("/path/to/other.wav", config)

        mock_model_class.assert_called_once_with("small", device="cpu", compute_type="int8")

    @patch("faster_whisper.WhisperModel")
    def test_a_different_model_reloads(self, mock_model_class):
        mock_model_class.return_value.transcribe.return_value = ([], None)

        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(model="small", device="cpu"))
        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(model="base", device="cpu"))

        self.assertEqual([call.args[0] for call in mock_model_class.call_args_list], ["small", "base"])

    @patch("faster_whisper.WhisperModel")
    def test_unload_drops_the_cached_model(self, mock_model_class):
        mock_model_class.return_value.transcribe.return_value = ([], None)
        config = TranscriptionConfig(device="cpu")

        self.engine.transcribe("/path/to/audio.wav", config)
        self.engine.unload()
        self.assertIsNone(self.engine._model)
        self.assertIsNone(self.engine._key)

        self.engine.transcribe("/path/to/audio.wav", config)

        self.assertEqual(mock_model_class.call_count, 2)

    @patch("faster_whisper.WhisperModel")
    def test_concurrent_calls_load_model_once(self, mock_model_class):
        """Concurrent transcriptions with same params should only load the model once."""
        mock_model_class.return_value.transcribe.return_value = ([whisper_segment(" Hello ", 0.0, 1.0)], None)

        barrier = threading.Barrier(4)
        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)
                self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(device="cpu"))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)

        self.assertEqual(errors, [])
        mock_model_class.assert_called_once_with("small", device="cpu", compute_type="int8")


class TestResolveWhisperCppBinary(unittest.TestCase):
    """Tests for the _resolve_whisper_cpp_binary() function."""

    def test_explicit_path_valid(self):
        """Test explicit path that exists."""
        with patch("os.path.isfile", return_value=True):
            result = _resolve_whisper_cpp_binary("/path/to/whisper-cli")

        self.assertEqual(result, "/path/to/whisper-cli")

    def test_explicit_path_invalid(self):
        """Test explicit path that doesn't exist."""
        with patch("os.path.isfile", return_value=False):
            with self.assertRaises(RuntimeError) as cm:
                _resolve_whisper_cpp_binary("/path/to/whisper-cli")

        self.assertIn("not found at", str(cm.exception))

    @patch.dict(os.environ, {"SYS2TXT_WHISPER_CPP": "/env/whisper-cli"})
    def test_env_var_valid(self):
        """Test environment variable path that exists."""
        with patch("os.path.isfile", return_value=True):
            result = _resolve_whisper_cpp_binary(None)

        self.assertEqual(result, "/env/whisper-cli")

    @patch.dict(os.environ, {"SYS2TXT_WHISPER_CPP": "/env/whisper-cli"})
    def test_env_var_invalid(self):
        """Test environment variable path that doesn't exist."""
        with patch("os.path.isfile", return_value=False):
            with self.assertRaises(RuntimeError) as cm:
                _resolve_whisper_cpp_binary(None)

        self.assertIn("SYS2TXT_WHISPER_CPP", str(cm.exception))

    @patch.dict(os.environ, {}, clear=True)
    def test_path_lookup_found(self):
        """Test PATH lookup succeeds."""
        with patch("shutil.which", return_value="/usr/bin/whisper-cli"):
            result = _resolve_whisper_cpp_binary(None)

        self.assertEqual(result, "/usr/bin/whisper-cli")

    @patch.dict(os.environ, {}, clear=True)
    def test_path_lookup_not_found(self):
        """Test PATH lookup fails."""
        with patch("shutil.which", return_value=None):
            with self.assertRaises(RuntimeError) as cm:
                _resolve_whisper_cpp_binary(None)

        self.assertIn("whisper-cli binary not found", str(cm.exception))


class TestResolveWhisperCppModelPath(unittest.TestCase):
    """Tests for the _resolve_whisper_cpp_model_path() function."""

    def test_explicit_path_valid(self):
        """Test explicit model path that exists."""
        with patch("os.path.isfile", return_value=True):
            result = _resolve_whisper_cpp_model_path("/path/to/model.bin", "small")

        self.assertEqual(result, "/path/to/model.bin")

    def test_explicit_path_invalid(self):
        """Test explicit model path that doesn't exist."""
        with patch("os.path.isfile", return_value=False):
            with self.assertRaises(RuntimeError) as cm:
                _resolve_whisper_cpp_model_path("/path/to/model.bin", "small")

        self.assertIn("not found at", str(cm.exception))

    @patch.dict(os.environ, {"SYS2TXT_WHISPER_CPP_MODELS": "/models"})
    def test_env_var_models_dir(self):
        """Test models directory from environment variable."""
        with patch("os.path.isfile", return_value=True):
            result = _resolve_whisper_cpp_model_path(None, "small")

        self.assertEqual(result, "/models/ggml-small.bin")

    @patch.dict(os.environ, {}, clear=True)
    def test_default_path(self):
        """Test default path in ~/.local/share/whisper.cpp/models/."""
        expected_path = Path.home() / ".local" / "share" / "whisper.cpp" / "models" / "ggml-tiny.bin"

        with patch.object(Path, "is_file", return_value=True):
            result = _resolve_whisper_cpp_model_path(None, "tiny")

        self.assertEqual(result, str(expected_path))

    @patch.dict(os.environ, {}, clear=True)
    def test_model_not_found(self):
        """Test model not found anywhere."""
        with patch("os.path.isfile", return_value=False):
            with patch.object(Path, "is_file", return_value=False):
                with self.assertRaises(RuntimeError) as cm:
                    _resolve_whisper_cpp_model_path(None, "small")

        self.assertIn("ggml-small.bin", str(cm.exception))


class TestParseWhisperCppOutput(unittest.TestCase):
    """Tests for the _parse_whisper_cpp_output() function."""

    def test_parse_keeps_cue_times(self):
        """Test parsing whisper.cpp output into cues that keep their times."""
        output = """[00:00:00.000 --> 00:00:05.120]   Hello world
[00:00:05.120 --> 00:00:10.240]   This is a test"""

        result = _parse_whisper_cpp_output(output)

        self.assertEqual(
            result.cues,
            (Cue(0.0, 5.12, "Hello world"), Cue(5.12, 10.24, "This is a test")),
        )

    def test_parse_records_the_language(self):
        """Test that the requested language is recorded on the transcript."""
        result = _parse_whisper_cpp_output("[00:00:00.000 --> 00:00:05.120]   Bonjour", "fr")

        self.assertEqual(result.language, "fr")

    def test_parse_empty_segments_ignored(self):
        """Test that empty segments are ignored."""
        output = """[00:00:00.000 --> 00:00:05.120]   Hello
[00:00:05.120 --> 00:00:10.240]
[00:00:10.240 --> 00:00:15.000]   World"""

        result = _parse_whisper_cpp_output(output)

        self.assertEqual(result.text, "Hello World")

    def test_parse_non_matching_lines_ignored(self):
        """Test that non-matching lines are ignored."""
        output = """whisper_init_from_file_no_state: loading model...
[00:00:00.000 --> 00:00:05.120]   Hello world
main: some debug output"""

        result = _parse_whisper_cpp_output(output)

        self.assertEqual(result.text, "Hello world")


class TestTimestampToSeconds(unittest.TestCase):
    """Tests for the _timestamp_to_seconds() function."""

    def test_simple_seconds(self):
        """Test simple seconds conversion."""
        self.assertAlmostEqual(_timestamp_to_seconds("00:00:05.120"), 5.12, places=3)

    def test_minutes_and_seconds(self):
        """Test minutes and seconds conversion."""
        self.assertAlmostEqual(_timestamp_to_seconds("00:02:30.500"), 150.5, places=3)

    def test_hours_minutes_seconds(self):
        """Test hours, minutes, and seconds conversion."""
        self.assertAlmostEqual(_timestamp_to_seconds("01:30:45.750"), 5445.75, places=3)


@patch("sys2txt.engines._resolve_whisper_cpp_binary", return_value="/path/to/whisper-cli")
@patch("sys2txt.engines._resolve_whisper_cpp_model_path", return_value="/path/to/model.bin")
class TestWhisperCppEngine(unittest.TestCase):
    """Tests for WhisperCppEngine."""

    def setUp(self):
        self.engine = WhisperCppEngine()

    @staticmethod
    def _stdout(mock_run, text="Hello world"):
        mock_run.return_value = MagicMock(stdout=f"[00:00:00.000 --> 00:00:05.000]   {text}\n", returncode=0)

    @patch("subprocess.run")
    def test_transcribe_success(self, mock_run, _model_path, _binary):
        """Test successful transcription."""
        self._stdout(mock_run)

        result = self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig())

        self.assertEqual(result.cues, (Cue(0.0, 5.0, "Hello world"),))
        mock_run.assert_called_once()

    @patch("subprocess.run")
    def test_transcribe_with_language(self, mock_run, _model_path, _binary):
        """Test transcription with language specified."""
        self._stdout(mock_run, "Bonjour")

        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(language="fr"))

        call_args = mock_run.call_args[0][0]
        self.assertIn("-l", call_args)
        self.assertIn("fr", call_args)

    @patch("subprocess.run")
    def test_transcribe_cpu_device(self, mock_run, _model_path, _binary):
        """Test transcription with CPU device adds --no-gpu flag."""
        self._stdout(mock_run)

        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(device="cpu"))

        self.assertIn("--no-gpu", mock_run.call_args[0][0])

    @patch("subprocess.run")
    def test_transcribe_vulkan_device(self, mock_run, _model_path, _binary):
        """Test transcription with Vulkan device does not add --no-gpu."""
        self._stdout(mock_run)

        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig(device="vulkan"))

        self.assertNotIn("--no-gpu", mock_run.call_args[0][0])

    @patch("subprocess.run")
    def test_transcribe_no_timestamps_does_not_pass_no_timestamps_flag(self, mock_run, _model_path, _binary):
        """Regression test for #42: --no-timestamps must never be passed to whisper-cli.

        whisper-cli only emits bracketed timestamp lines when timestamps are enabled;
        with --no-timestamps its plain-text output doesn't match the parser's regex,
        so the transcript would silently come back empty.
        """
        self._stdout(mock_run)

        result = self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig())

        self.assertNotIn("--no-timestamps", mock_run.call_args[0][0])
        self.assertEqual(result.text, "Hello world")

    @patch("subprocess.run")
    def test_transcribe_passes_the_configured_paths(self, mock_run, mock_model_path, mock_binary):
        """The engine resolves the binary and model from the config, not from arguments."""
        self._stdout(mock_run)
        config = TranscriptionConfig(model_path="/custom/model.bin", whisper_cpp_path="/custom/whisper-cli")

        self.engine.transcribe("/path/to/audio.wav", config)

        mock_binary.assert_called_once_with("/custom/whisper-cli")
        mock_model_path.assert_called_once_with("/custom/model.bin", "small")

    @patch("subprocess.run")
    def test_transcribe_failure(self, mock_run, _model_path, _binary):
        """Test transcription failure raises RuntimeError."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "whisper-cli", stderr="Error: model not found")

        with self.assertRaises(RuntimeError) as cm:
            self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig())

        self.assertIn("whisper-cli failed", str(cm.exception))

    @patch("subprocess.run")
    def test_transcribe_timeout_raises_runtime_error(self, mock_run, _model_path, _binary):
        """Test that a hung whisper-cli process raises RuntimeError after timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="whisper-cli", timeout=300)

        with self.assertRaises(RuntimeError) as cm:
            self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig())

        self.assertIn("timed out", str(cm.exception))

    def test_is_available(self, _model_path, _binary):
        self.assertTrue(self.engine.is_available())

    @patch.dict(os.environ, {}, clear=True)
    def test_is_not_available_without_a_binary(self, _model_path, mock_binary):
        mock_binary.side_effect = RuntimeError("whisper-cli binary not found")

        self.assertFalse(self.engine.is_available())


if __name__ == "__main__":
    unittest.main()
