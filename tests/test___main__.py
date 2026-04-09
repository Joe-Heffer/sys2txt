"""Tests for helper functions in sys2txt.__main__."""

import os
import unittest
from argparse import Namespace
from unittest.mock import mock_open, patch

from sys2txt.__main__ import _build_transcription_config, _resolve_output_path, _save_transcript
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
