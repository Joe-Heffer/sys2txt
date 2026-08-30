"""Tests for sys2txt.engines module."""

import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
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
    _download_whisper_cpp_model,
    _parse_whisper_cpp_json,
    _resolve_device,
    _resolve_whisper_cpp_binary,
    _resolve_whisper_cpp_model_path,
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
    def test_model_not_found_download_disabled(self):
        """Test model not found anywhere and downloading is disabled."""
        with patch("os.path.isfile", return_value=False):
            with patch.object(Path, "is_file", return_value=False):
                with self.assertRaises(RuntimeError) as cm:
                    _resolve_whisper_cpp_model_path(None, "small", download=False)

        self.assertIn("ggml-small.bin", str(cm.exception))

    @patch("sys2txt.engines._download_whisper_cpp_model")
    def test_model_missing_downloads_it(self, mock_download):
        """Test a missing model is downloaded to the default directory."""
        expected_path = Path.home() / ".local" / "share" / "whisper.cpp" / "models" / "ggml-small.bin"

        with patch("os.path.isfile", return_value=False):
            with patch.object(Path, "is_file", return_value=False):
                result = _resolve_whisper_cpp_model_path(None, "small")

        mock_download.assert_called_once_with("ggml-small.bin", expected_path)
        self.assertEqual(result, str(expected_path))

    @patch.dict(os.environ, {"SYS2TXT_WHISPER_CPP_MODELS": "/models"})
    @patch("sys2txt.engines._download_whisper_cpp_model")
    def test_model_missing_downloads_to_env_dir(self, mock_download):
        """Test a missing model is downloaded to SYS2TXT_WHISPER_CPP_MODELS if set."""
        with patch("os.path.isfile", return_value=False):
            result = _resolve_whisper_cpp_model_path(None, "small")

        mock_download.assert_called_once_with("ggml-small.bin", Path("/models/ggml-small.bin"))
        self.assertEqual(result, "/models/ggml-small.bin")

    @patch("sys2txt.engines._download_whisper_cpp_model")
    def test_download_failure_falls_back_to_error(self, mock_download):
        """Test a failed download still raises the original 'not found' error."""
        mock_download.side_effect = RuntimeError("network unreachable")

        with patch("os.path.isfile", return_value=False):
            with patch.object(Path, "is_file", return_value=False):
                with self.assertRaises(RuntimeError) as cm:
                    _resolve_whisper_cpp_model_path(None, "small")

        self.assertIn("ggml-small.bin", str(cm.exception))


class TestDownloadWhisperCppModel(unittest.TestCase):
    """Tests for the _download_whisper_cpp_model() function."""

    def test_downloads_and_renames_into_place(self):
        """Test the body is streamed to a .part file and renamed on success."""
        response = MagicMock()
        response.getheader.return_value = None
        response.read.side_effect = [b"chunk1", b"chunk2", b""]
        response.__enter__.return_value = response

        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "models" / "ggml-small.bin"
            with patch("urllib.request.urlopen", return_value=response):
                _download_whisper_cpp_model("ggml-small.bin", destination)

            self.assertTrue(destination.is_file())
            self.assertEqual(destination.read_bytes(), b"chunk1chunk2")
            self.assertFalse(destination.with_suffix(".bin.part").exists())

    def test_download_failure_removes_partial_file(self):
        """Test a network failure raises RuntimeError and cleans up the .part file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            destination = Path(tmpdir) / "models" / "ggml-small.bin"
            with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("boom")):
                with self.assertRaises(RuntimeError) as cm:
                    _download_whisper_cpp_model("ggml-small.bin", destination)

            self.assertIn("Failed to download", str(cm.exception))
            self.assertFalse((destination.parent / "ggml-small.bin.part").exists())


def whisper_cpp_json(segments, language=None):
    """Build a whisper-cli ``-oj`` JSON document as a string.

    Args:
        segments: Iterable of (text, start_seconds, end_seconds) tuples
        language: Value to put under result.language, or omitted if None
    """
    transcription = []
    for text, start, end in segments:
        transcription.append(
            {
                "timestamps": {
                    "from": f"{start:012.3f}",  # display-only, not parsed
                    "to": f"{end:012.3f}",
                },
                "offsets": {"from": int(start * 1000), "to": int(end * 1000)},
                "text": text,
            }
        )
    doc = {"transcription": transcription}
    if language is not None:
        doc["result"] = {"language": language}
    return json.dumps(doc)


class TestParseWhisperCppJson(unittest.TestCase):
    """Tests for the _parse_whisper_cpp_json() function."""

    def test_parse_keeps_cue_times(self):
        """Test parsing whisper.cpp JSON into cues that keep their times."""
        raw = whisper_cpp_json([("Hello world", 0.0, 5.12), ("This is a test", 5.12, 10.24)])

        result = _parse_whisper_cpp_json(raw)

        self.assertEqual(
            result.cues,
            (Cue(0.0, 5.12, "Hello world"), Cue(5.12, 10.24, "This is a test")),
        )

    def test_parse_prefers_detected_language_over_the_requested_one(self):
        """whisper.cpp's own result.language wins over the caller's requested language."""
        raw = whisper_cpp_json([("Bonjour", 0.0, 5.12)], language="fr")

        result = _parse_whisper_cpp_json(raw, "en")

        self.assertEqual(result.language, "fr")

    def test_parse_falls_back_to_requested_language_without_a_detected_one(self):
        """Without a result.language field, the requested language is recorded instead."""
        raw = whisper_cpp_json([("Bonjour", 0.0, 5.12)])

        result = _parse_whisper_cpp_json(raw, "fr")

        self.assertEqual(result.language, "fr")

    def test_parse_empty_segments_ignored(self):
        """Test that empty segments are ignored."""
        raw = whisper_cpp_json([("Hello", 0.0, 5.12), ("", 5.12, 10.24), ("World", 10.24, 15.0)])

        result = _parse_whisper_cpp_json(raw)

        self.assertEqual(result.text, "Hello World")

    def test_parse_malformed_json_raises(self):
        """A body that isn't the documented JSON shape is a failure, not silent empty output."""
        with self.assertRaises(RuntimeError):
            _parse_whisper_cpp_json("not json")

    def test_parse_missing_transcription_key_raises(self):
        """Valid JSON that lacks the expected shape is still a failure."""
        with self.assertRaises(RuntimeError):
            _parse_whisper_cpp_json(json.dumps({"unexpected": []}))


@patch("sys2txt.engines._resolve_whisper_cpp_binary", return_value="/path/to/whisper-cli")
@patch("sys2txt.engines._resolve_whisper_cpp_model_path", return_value="/path/to/model.bin")
class TestWhisperCppEngine(unittest.TestCase):
    """Tests for WhisperCppEngine."""

    def setUp(self):
        self.engine = WhisperCppEngine()

    @staticmethod
    def _stdout(mock_run, text="Hello world"):
        """Make the mocked whisper-cli write the JSON file its ``-of``/``-oj`` args request."""

        def write_json(cmd, **kwargs):
            output_prefix = cmd[cmd.index("-of") + 1]
            Path(output_prefix + ".json").write_text(whisper_cpp_json([(text, 0.0, 5.0)]))
            return MagicMock(returncode=0)

        mock_run.side_effect = write_json

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
    def test_transcribe_requests_json_output(self, mock_run, _model_path, _binary):
        """Test that whisper-cli is asked for -oj JSON rather than relying on stdout."""
        self._stdout(mock_run)

        self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig())

        call_args = mock_run.call_args[0][0]
        self.assertIn("-oj", call_args)
        self.assertIn("-of", call_args)

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
    def test_transcribe_missing_json_output_raises(self, mock_run, _model_path, _binary):
        """If whisper-cli exits successfully but never writes the JSON file, that's a failure."""
        mock_run.return_value = MagicMock(returncode=0)

        with self.assertRaises(RuntimeError):
            self.engine.transcribe("/path/to/audio.wav", TranscriptionConfig())

    @patch("subprocess.run")
    def test_transcribe_passes_the_configured_paths(self, mock_run, mock_model_path, mock_binary):
        """The engine resolves the binary and model from the config, not from arguments."""
        self._stdout(mock_run)
        config = TranscriptionConfig(model_path="/custom/model.bin", whisper_cpp_path="/custom/whisper-cli")

        self.engine.transcribe("/path/to/audio.wav", config)

        mock_binary.assert_called_once_with("/custom/whisper-cli")
        mock_model_path.assert_called_once_with("/custom/model.bin", "small", download=True)

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
