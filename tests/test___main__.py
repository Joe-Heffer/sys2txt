"""Tests for sys2txt.__main__ module."""

import logging
import os
import unittest
from argparse import Namespace
from unittest.mock import mock_open, patch

from sys2txt.__main__ import (
    _build_transcription_config,
    _configure_logging,
    _resolve_output_path,
    _save_transcript,
    main,
)
from sys2txt.transcribe import TranscriptionConfig


class TestResolveOutputPath(unittest.TestCase):
    def test_explicit_arg_returned_as_is(self):
        result = _resolve_output_path("/tmp/my_output.txt")
        self.assertEqual(result, "/tmp/my_output.txt")

    def test_none_generates_timestamped_path(self):
        with (
            patch("sys2txt.__main__.ensure_output_dir", return_value="/out"),
            patch("sys2txt.__main__.get_timestamp_filename", return_value="2024-01-01_00-00-00.txt"),
        ):
            result = _resolve_output_path(None)
        self.assertEqual(result, os.path.join("/out", "2024-01-01_00-00-00.txt"))


class TestBuildTranscriptionConfig(unittest.TestCase):
    def test_returns_config_with_correct_values(self):
        args = Namespace(
            engine="faster",
            model_size="small",
            language="en",
            timestamps=True,
            model_path="/models/ggml.bin",
            whisper_cpp_path="/usr/local/bin/whisper-cli",
            device="cpu",
        )
        config = _build_transcription_config(args)
        self.assertIsInstance(config, TranscriptionConfig)
        self.assertEqual(config.engine, "faster")
        self.assertEqual(config.model, "small")
        self.assertEqual(config.language, "en")
        self.assertTrue(config.timestamps)
        self.assertEqual(config.model_path, "/models/ggml.bin")
        self.assertEqual(config.whisper_cpp_path, "/usr/local/bin/whisper-cli")
        self.assertEqual(config.device, "cpu")


class TestSaveTranscript(unittest.TestCase):
    def test_prints_text_writes_file_and_logs(self):
        m = mock_open()
        with (
            patch("builtins.open", m),
            patch("builtins.print") as mock_print,
            patch("sys2txt.__main__.logger") as mock_logger,
        ):
            _save_transcript("hello world", "/out/transcript.txt")

        mock_print.assert_called_once_with("hello world")
        m.assert_called_once_with("/out/transcript.txt", "w", encoding="utf-8")
        m().write.assert_called_once_with("hello world\n")
        mock_logger.info.assert_called_once_with("Transcript saved to: %s", "/out/transcript.txt")


class TestArgumentParsing(unittest.TestCase):
    """Tests for CLI argument parsing."""

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.record_once")
    @patch("sys2txt.__main__.transcribe_file", return_value="text")
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_defaults(self, _res, _save, _trans, _rec, _src, _log):
        with patch("sys.argv", ["sys2txt", "once"]):
            main()
        # record_once was called (no --input), meaning mode dispatched correctly
        _rec.assert_called_once()

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.segment_and_transcribe_live")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_live_defaults(self, _res, _live, _src, _log):
        with patch("sys.argv", ["sys2txt", "live"]):
            main()
        _live.assert_called_once()
        call_kwargs = _live.call_args
        self.assertEqual(call_kwargs[1]["segment_seconds"], 8)
        self.assertEqual(call_kwargs[1]["silence_timeout"], 0)

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_file", return_value="text")
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_with_input_skips_recording(self, _res, _save, _trans, _src, _log):
        with (
            patch("sys.argv", ["sys2txt", "once", "--input", "/tmp/audio.wav"]),
            patch("sys2txt.__main__.record_once") as mock_rec,
        ):
            main()
        mock_rec.assert_not_called()
        _trans.assert_called_once_with("/tmp/audio.wav", unittest.mock.ANY)

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.record_once")
    @patch("sys2txt.__main__.transcribe_file", return_value="text")
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_all_flags(self, _res, _save, _trans, _rec, _src, _log):
        with patch(
            "sys.argv",
            [
                "sys2txt",
                "--verbose",
                "once",
                "--source",
                "my.monitor",
                "--model",
                "large-v2",
                "--engine",
                "faster",
                "--language",
                "en",
                "--timestamps",
                "--device",
                "cuda",
                "--duration",
                "30",
                "--output",
                "/tmp/my.txt",
            ],
        ):
            main()
        # Source should be the explicit one, not the default
        _src.assert_not_called()
        call_args = _rec.call_args
        self.assertEqual(call_args[1]["source"], "my.monitor")
        self.assertEqual(call_args[1]["duration"], 30)
        # Output was explicitly provided so _resolve_output_path gets it
        _res.assert_called_once_with("/tmp/my.txt")

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.segment_and_transcribe_live")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_live_all_flags(self, _res, _live, _src, _log):
        with patch(
            "sys.argv",
            [
                "sys2txt",
                "--quiet",
                "live",
                "--source",
                "my.monitor",
                "--model",
                "tiny",
                "--engine",
                "cpp",
                "--language",
                "fr",
                "--timestamps",
                "--device",
                "vulkan",
                "--model-path",
                "/models/ggml.bin",
                "--whisper-cpp-path",
                "/usr/bin/whisper-cli",
                "--segment-seconds",
                "15",
                "--output",
                "/tmp/live.txt",
                "--silence-timeout",
                "30",
            ],
        ):
            main()
        _live.assert_called_once()
        call_kwargs = _live.call_args[1]
        self.assertEqual(call_kwargs["source"], "my.monitor")
        self.assertEqual(call_kwargs["segment_seconds"], 15)
        self.assertEqual(call_kwargs["silence_timeout"], 30)
        self.assertEqual(call_kwargs["output_path"], "/tmp/out.txt")

    def test_missing_subcommand_exits(self):
        with patch("sys.argv", ["sys2txt"]):
            with self.assertRaises(SystemExit):
                main()


class TestListSources(unittest.TestCase):
    """Tests for --list-sources flag."""

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.list_pulse_sources", return_value=[("source1", "desc1"), ("source2", "desc2")])
    def test_list_sources_prints_and_returns(self, _sources, _log):
        with (
            patch("sys.argv", ["sys2txt", "once", "--list-sources"]),
            patch("builtins.print") as mock_print,
        ):
            main()
        mock_print.assert_any_call("Available PulseAudio sources:")
        mock_print.assert_any_call("  ", "source1")
        mock_print.assert_any_call("  ", "source2")

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.list_pulse_sources", return_value=[])
    def test_list_sources_empty_exits(self, _sources, _log):
        with patch("sys.argv", ["sys2txt", "once", "--list-sources"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
            self.assertEqual(ctx.exception.code, 1)


class TestModeDispatchOnce(unittest.TestCase):
    """Tests for once mode dispatch logic."""

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.record_once")
    @patch("sys2txt.__main__.transcribe_file", return_value="hello world")
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_records_then_transcribes(self, _res, mock_save, mock_trans, mock_rec, _src, _log):
        with patch("sys.argv", ["sys2txt", "once"]):
            main()
        mock_rec.assert_called_once()
        mock_trans.assert_called_once()
        mock_save.assert_called_once_with("hello world", "/tmp/out.txt")

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_file", return_value="from file")
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_input_skips_recording(self, _res, mock_save, mock_trans, _src, _log):
        with patch("sys.argv", ["sys2txt", "once", "--input", "/audio.wav"]):
            main()
        mock_trans.assert_called_once()
        self.assertEqual(mock_trans.call_args[0][0], "/audio.wav")
        mock_save.assert_called_once_with("from file", "/tmp/out.txt")


class TestModeDispatchLive(unittest.TestCase):
    """Tests for live mode dispatch logic."""

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.segment_and_transcribe_live")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_live_calls_segment_and_transcribe(self, _res, mock_live, _src, _log):
        with patch("sys.argv", ["sys2txt", "live"]):
            main()
        mock_live.assert_called_once()
        kwargs = mock_live.call_args[1]
        self.assertEqual(kwargs["source"], "default.monitor")
        self.assertEqual(kwargs["sample_rate"], 16000)
        self.assertEqual(kwargs["channels"], 1)
        self.assertEqual(kwargs["segment_seconds"], 8)
        self.assertEqual(kwargs["output_path"], "/tmp/out.txt")
        self.assertEqual(kwargs["silence_timeout"], 0)
        self.assertTrue(callable(kwargs["transcribe_callback"]))


class TestConfigureLogging(unittest.TestCase):
    """Tests for _configure_logging()."""

    def setUp(self):
        """Remove handlers added by _configure_logging between tests."""
        root = logging.getLogger()
        self._original_handlers = root.handlers[:]
        self._original_level = root.level

    def tearDown(self):
        root = logging.getLogger()
        root.handlers = self._original_handlers
        root.level = self._original_level

    def test_verbose_sets_debug(self):
        _configure_logging(verbose=True, quiet=False)
        self.assertEqual(logging.getLogger().level, logging.DEBUG)

    def test_quiet_sets_warning(self):
        _configure_logging(verbose=False, quiet=True)
        self.assertEqual(logging.getLogger().level, logging.WARNING)

    def test_default_sets_info(self):
        _configure_logging(verbose=False, quiet=False)
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_log_level_env_overrides_flags(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "ERROR"}):
            _configure_logging(verbose=True, quiet=False)
        self.assertEqual(logging.getLogger().level, logging.ERROR)
