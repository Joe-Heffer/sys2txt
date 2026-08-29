"""Tests for sys2txt.__main__ module."""

import logging
import os
import tempfile
import unittest
from argparse import Namespace
from unittest.mock import mock_open, patch

from sys2txt.__main__ import (
    Options,
    _build_options,
    _build_transcription_config,
    _configure_logging,
    _format_segment,
    _resolve_output_path,
    _save_transcript,
    main,
)
from sys2txt.pipeline import TranscriptSegment
from sys2txt.transcribe import TranscriptionConfig


def make_args(**overrides):
    """Build a parsed-argument namespace with the CLI's defaults."""
    values = dict(
        mode="live",
        source=None,
        model_size="small",
        engine="auto",
        device="auto",
        language=None,
        timestamps=False,
        list_sources=False,
        model_path=None,
        whisper_cpp_path=None,
        output=None,
        segment_seconds=8,
        silence_timeout=0,
    )
    values.update(overrides)
    return Namespace(**values)


class Failure:
    """Marker for live_segments(): emit a failed segment instead of transcribed text."""

    def __init__(self, reason="transcription timed out after 60s"):
        self.reason = reason


def live_segments(*items, segment_seconds=8, indices=None):
    """Yield TranscriptSegment values the way transcribe_live does.

    Each item is either transcript text or a Failure marker. Pass indices to place the
    segments on the timeline non-contiguously, as happens when empty segments are skipped.
    """
    for position, item in enumerate(items):
        index = indices[position] if indices else position
        start = index * segment_seconds
        failed = isinstance(item, Failure)
        yield TranscriptSegment(
            index=index,
            text="" if failed else item,
            start=float(start),
            end=float(start + segment_seconds),
            error=item.reason if failed else None,
        )


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


class TestBuildOptions(unittest.TestCase):
    """Tests for the parsing/behaviour boundary."""

    def test_copies_arguments_onto_options(self):
        args = make_args(
            mode="once",
            source="my.monitor",
            model_size="large-v2",
            engine="cpp",
            device="cuda",
            language="en",
            timestamps=True,
            model_path="/models/ggml.bin",
            whisper_cpp_path="/usr/local/bin/whisper-cli",
            output="/tmp/out.txt",
            duration=30,
            input=None,
        )
        options = _build_options(args)
        self.assertIsInstance(options, Options)
        self.assertEqual(options.mode, "once")
        self.assertEqual(options.source, "my.monitor")
        self.assertEqual(options.model, "large-v2")
        self.assertEqual(options.engine, "cpp")
        self.assertEqual(options.device, "cuda")
        self.assertEqual(options.language, "en")
        self.assertTrue(options.timestamps)
        self.assertEqual(options.model_path, "/models/ggml.bin")
        self.assertEqual(options.whisper_cpp_path, "/usr/local/bin/whisper-cli")
        self.assertEqual(options.output, "/tmp/out.txt")
        self.assertEqual(options.duration, 30)

    def test_missing_input_file_is_rejected(self):
        args = make_args(mode="once", duration=None, input="/does/not/exist.wav")
        with self.assertRaises(ValueError) as ctx:
            _build_options(args)
        self.assertIn("--input", str(ctx.exception))

    def test_existing_input_file_is_accepted(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            args = make_args(mode="once", duration=None, input=f.name)
            options = _build_options(args)
        self.assertEqual(options.input_path, f.name)

    def test_non_positive_duration_is_rejected(self):
        args = make_args(mode="once", duration=0, input=None)
        with self.assertRaises(ValueError):
            _build_options(args)

    def test_non_positive_segment_seconds_is_rejected(self):
        with self.assertRaises(ValueError):
            _build_options(make_args(segment_seconds=0))

    def test_negative_silence_timeout_is_rejected(self):
        with self.assertRaises(ValueError):
            _build_options(make_args(silence_timeout=-1))

    def test_silence_timeout_shorter_than_a_segment_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _build_options(make_args(segment_seconds=8, silence_timeout=3))
        self.assertIn("--silence-timeout", str(ctx.exception))

    def test_silence_timeout_equal_to_segment_length_is_accepted(self):
        options = _build_options(make_args(segment_seconds=8, silence_timeout=8))
        self.assertEqual(options.silence_timeout, 8)

    def test_warns_about_cpp_only_flags(self):
        args = make_args(engine="faster", model_path="/m.bin", whisper_cpp_path="/w")
        with self.assertLogs("sys2txt.__main__", level="WARNING") as logs:
            _build_options(args)
        self.assertEqual(len(logs.output), 2)


class TestBuildTranscriptionConfig(unittest.TestCase):
    def test_returns_config_with_correct_values(self):
        options = Options(
            mode="once",
            engine="faster",
            model="small",
            language="en",
            timestamps=True,
            model_path="/models/ggml.bin",
            whisper_cpp_path="/usr/local/bin/whisper-cli",
            device="cpu",
        )
        config = _build_transcription_config(options)
        self.assertIsInstance(config, TranscriptionConfig)
        self.assertEqual(config.engine, "faster")
        self.assertEqual(config.model, "small")
        self.assertEqual(config.language, "en")
        self.assertTrue(config.timestamps)
        self.assertEqual(config.model_path, "/models/ggml.bin")
        self.assertEqual(config.whisper_cpp_path, "/usr/local/bin/whisper-cli")
        self.assertEqual(config.device, "cpu")


class TestFormatSegment(unittest.TestCase):
    """Tests for live output formatting."""

    def test_plain_text_without_timestamps(self):
        segment = TranscriptSegment(index=1, text="  hello  ", start=8.0, end=16.0)
        self.assertEqual(_format_segment(segment, timestamps=False), "hello")

    def test_timestamp_prefix(self):
        segment = TranscriptSegment(index=1, text="hello", start=8.0, end=16.0)
        self.assertEqual(_format_segment(segment, timestamps=True), "[    8-   16s] hello")


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
    @patch("sys2txt.__main__.transcribe_once", return_value="text")
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_defaults(self, _res, _save, mock_once, _src, _log):
        with patch("sys.argv", ["sys2txt", "once"]):
            main()
        mock_once.assert_called_once()
        self.assertEqual(mock_once.call_args[0][0], "default.monitor")
        self.assertIsNone(mock_once.call_args[0][2])

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_live", return_value=iter(()))
    @patch("sys2txt.__main__._resolve_output_path")
    def test_live_defaults(self, mock_res, mock_live, _src, _log):
        with tempfile.TemporaryDirectory() as tmp:
            mock_res.return_value = os.path.join(tmp, "out.txt")
            mock_live.return_value = live_segments()
            with patch("sys.argv", ["sys2txt", "live"]):
                main()
        mock_live.assert_called_once()
        self.assertEqual(mock_live.call_args[1]["segment_seconds"], 8)

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_file", return_value="text")
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_with_input_skips_recording(self, _res, _save, mock_trans, _src, _log):
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            with (
                patch("sys.argv", ["sys2txt", "once", "--input", audio.name]),
                patch("sys2txt.__main__.transcribe_once") as mock_once,
            ):
                main()
            mock_once.assert_not_called()
            mock_trans.assert_called_once_with(audio.name, unittest.mock.ANY)

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_once", return_value="text")
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_all_flags(self, _res, _save, mock_once, _src, _log):
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
        self.assertEqual(mock_once.call_args[0][0], "my.monitor")
        self.assertEqual(mock_once.call_args[0][2], 30)
        # Output was explicitly provided so _resolve_output_path gets it
        _res.assert_called_once_with("/tmp/my.txt")

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_live")
    @patch("sys2txt.__main__._resolve_output_path")
    def test_live_all_flags(self, mock_res, mock_live, _src, _log):
        with tempfile.TemporaryDirectory() as tmp:
            mock_res.return_value = os.path.join(tmp, "out.txt")
            mock_live.return_value = live_segments()
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
        mock_live.assert_called_once()
        self.assertEqual(mock_live.call_args[0][0], "my.monitor")
        self.assertEqual(mock_live.call_args[1]["segment_seconds"], 15)
        config = mock_live.call_args[0][1]
        self.assertEqual(config.model, "tiny")
        self.assertEqual(config.engine, "cpp")

    def test_missing_subcommand_exits(self):
        with patch("sys.argv", ["sys2txt"]):
            with self.assertRaises(SystemExit):
                main()

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_once", side_effect=KeyboardInterrupt())
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_keyboard_interrupt_exits_cleanly(self, _res, _once, _src, _log):
        with patch("sys.argv", ["sys2txt", "once"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 130)

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", side_effect=RuntimeError("boom"))
    def test_runtime_error_exits_with_code_1(self, _src, _log):
        with patch("sys.argv", ["sys2txt", "once"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)


class TestInvalidArguments(unittest.TestCase):
    """Invalid flag combinations fail fast with a usage error."""

    def _assert_usage_error(self, argv):
        with patch("sys2txt.__main__._configure_logging"):
            with patch("sys.argv", argv):
                with self.assertRaises(SystemExit) as ctx:
                    main()
        self.assertEqual(ctx.exception.code, 2)

    def test_missing_input_file(self):
        self._assert_usage_error(["sys2txt", "once", "--input", "/does/not/exist.wav"])

    def test_non_positive_duration(self):
        self._assert_usage_error(["sys2txt", "once", "--duration", "0"])

    def test_non_positive_segment_seconds(self):
        self._assert_usage_error(["sys2txt", "live", "--segment-seconds", "0"])

    def test_silence_timeout_shorter_than_segment(self):
        self._assert_usage_error(["sys2txt", "live", "--segment-seconds", "8", "--silence-timeout", "3"])


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
    @patch("sys2txt.__main__.transcribe_once", return_value="hello world")
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_records_then_transcribes(self, _res, mock_save, mock_once, _src, _log):
        with patch("sys.argv", ["sys2txt", "once"]):
            main()
        mock_once.assert_called_once()
        mock_save.assert_called_once_with("hello world", "/tmp/out.txt")

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_file", return_value="from file")
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_input_skips_recording(self, _res, mock_save, mock_trans, _src, _log):
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            with patch("sys.argv", ["sys2txt", "once", "--input", audio.name]):
                main()
            self.assertEqual(mock_trans.call_args[0][0], audio.name)
        mock_save.assert_called_once_with("from file", "/tmp/out.txt")


class TestModeDispatchLive(unittest.TestCase):
    """Tests for live mode consumption of the transcript stream."""

    def setUp(self):
        self.exit_code = 0

    def _run_live(self, argv, segments):
        """Run the CLI in live mode against a canned segment stream, returning the transcript file.

        A non-zero exit is recorded in self.exit_code rather than raised, so the transcript
        written before the CLI gave up can still be inspected.
        """
        with tempfile.TemporaryDirectory() as tmp:
            output_file = os.path.join(tmp, "out.txt")
            with (
                patch("sys2txt.__main__._configure_logging"),
                patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor"),
                patch("sys2txt.__main__._resolve_output_path", return_value=output_file),
                patch("sys2txt.__main__.transcribe_live", return_value=segments) as mock_live,
                patch("builtins.print") as mock_print,
                patch("sys.argv", argv),
            ):
                try:
                    main()
                except SystemExit as e:
                    self.exit_code = e.code
            with open(output_file, encoding="utf-8") as f:
                written = f.read()
        return mock_live, mock_print, written

    def test_prints_and_saves_each_segment(self):
        _, mock_print, written = self._run_live(
            ["sys2txt", "live"],
            live_segments("hello", "world"),
        )
        mock_print.assert_any_call("hello", flush=True)
        mock_print.assert_any_call("world", flush=True)
        self.assertEqual(written, "hello\nworld\n")

    def test_timestamps_prefix_each_line(self):
        _, _, written = self._run_live(
            ["sys2txt", "live", "--timestamps"],
            live_segments("hello", "world"),
        )
        self.assertEqual(written, "[    0-    8s] hello\n[    8-   16s] world\n")

    def test_silence_timeout_stops_consuming(self):
        segments = live_segments("", "", "should never be reached")
        _, mock_print, written = self._run_live(
            ["sys2txt", "live", "--silence-timeout", "16"],
            segments,
        )
        self.assertEqual(written, "\n\n")
        self.assertEqual(mock_print.call_count, 2)

    def test_silence_counter_resets_on_speech(self):
        segments = live_segments("", "hello", "", "")
        _, mock_print, written = self._run_live(
            ["sys2txt", "live", "--silence-timeout", "16"],
            segments,
        )
        # Silence resets at "hello", so all four segments are consumed
        self.assertEqual(written, "\nhello\n\n\n")
        self.assertEqual(mock_print.call_count, 4)

    def test_silence_timeout_disabled_by_default(self):
        _, mock_print, written = self._run_live(
            ["sys2txt", "live"],
            live_segments("", "", ""),
        )
        self.assertEqual(mock_print.call_count, 3)
        self.assertEqual(written, "\n\n\n")

    def test_silence_measured_across_gaps_in_the_timeline(self):
        """Silence is measured on the recording's timeline, not by counting segments."""
        # One silent segment at 0-8s, the next at 24-32s: 32s of quiet in two segments
        segments = live_segments("", "", "should never be reached", indices=[0, 3, 4])
        _, mock_print, _ = self._run_live(
            ["sys2txt", "live", "--silence-timeout", "24"],
            segments,
        )
        self.assertEqual(mock_print.call_count, 2)
        self.assertEqual(self.exit_code, 0)

    def test_failures_do_not_count_as_silence(self):
        """Transcription failures never accumulate towards the silence timeout."""
        segments = live_segments(Failure(), "", Failure(), "", Failure(), "hello")
        _, mock_print, written = self._run_live(
            ["sys2txt", "live", "--silence-timeout", "16"],
            segments,
        )
        self.assertEqual(mock_print.call_count, 6)
        self.assertEqual(written, "\n\n\n\n\n" + "hello\n")
        self.assertEqual(self.exit_code, 0)

    def test_repeated_failures_stop_with_an_error(self):
        """A persistent failure is reported as a failure, not as silence."""
        segments = live_segments(Failure(), Failure(), Failure(), "should never be reached")
        with self.assertLogs("sys2txt.__main__", level="ERROR") as logs:
            _, mock_print, written = self._run_live(
                ["sys2txt", "live", "--silence-timeout", "16"],
                segments,
            )

        self.assertEqual(self.exit_code, 1)
        self.assertEqual(mock_print.call_count, 3)
        self.assertIn("3 consecutive segments", logs.output[0])
        self.assertIn("timed out", logs.output[0])
        # The transcript produced before giving up is still saved
        self.assertEqual(written, "\n\n\n")

    def test_recovered_failures_do_not_stop_the_run(self):
        """The failure counter only fires on consecutive failures."""
        segments = live_segments(Failure(), Failure(), "hello", Failure(), Failure())
        _, mock_print, written = self._run_live(["sys2txt", "live"], segments)

        self.assertEqual(mock_print.call_count, 5)
        self.assertEqual(written, "\n\nhello\n\n\n")
        self.assertEqual(self.exit_code, 0)

    def test_keyboard_interrupt_saves_what_was_transcribed(self):
        def segments():
            yield from live_segments("hello")
            raise KeyboardInterrupt()

        with tempfile.TemporaryDirectory() as tmp:
            output_file = os.path.join(tmp, "out.txt")
            with (
                patch("sys2txt.__main__._configure_logging"),
                patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor"),
                patch("sys2txt.__main__._resolve_output_path", return_value=output_file),
                patch("sys2txt.__main__.transcribe_live", return_value=segments()),
                patch("builtins.print"),
                patch("sys.argv", ["sys2txt", "live"]),
            ):
                main()  # exits normally, not with code 130
            with open(output_file, encoding="utf-8") as f:
                self.assertEqual(f.read(), "hello\n")

    def test_closes_the_transcript_stream_when_stopping_early(self):
        segments = live_segments("", "", "unreachable")
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("sys2txt.__main__._configure_logging"),
                patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor"),
                patch("sys2txt.__main__._resolve_output_path", return_value=os.path.join(tmp, "out.txt")),
                patch("sys2txt.__main__.transcribe_live", return_value=segments),
                patch("builtins.print"),
                patch("sys.argv", ["sys2txt", "live", "--silence-timeout", "16"]),
            ):
                main()
        with self.assertRaises(StopIteration):
            next(segments)


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

    def test_default_sets_warning(self):
        _configure_logging(verbose=False, quiet=False)
        self.assertEqual(logging.getLogger().level, logging.WARNING)

    def test_log_level_env_overrides_flags(self):
        with patch.dict(os.environ, {"LOG_LEVEL": "ERROR"}):
            _configure_logging(verbose=True, quiet=False)
        self.assertEqual(logging.getLogger().level, logging.ERROR)


if __name__ == "__main__":
    unittest.main()
