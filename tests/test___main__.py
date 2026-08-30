"""Tests for sys2txt.__main__ module."""

import json
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
    _check_output_writable,
    _configure_logging,
    _format_segment,
    _resolve_output_path,
    _save_transcript,
    main,
)
from sys2txt.formats import Cue, Transcript
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
        no_download=False,
        output=None,
        segment_seconds=8,
        silence_timeout=0,
        max_lag=0.0,
        on_lag=None,
        output_format="txt",
    )
    values.update(overrides)
    return Namespace(**values)


class Failure:
    """Marker for live_segments(): emit a failed segment instead of transcribed text."""

    def __init__(self, reason="transcription timed out after 60s"):
        self.reason = reason


def live_segments(*items, segment_seconds=8, indices=None, lags=(), dropped=()):
    """Yield TranscriptSegment values the way transcribe_live does.

    Each item is either transcript text or a Failure marker. A spoken segment carries one cue
    two seconds long, already rebased onto the recording timeline; a silent or failed segment
    carries none. Pass indices to place the segments on the timeline non-contiguously, as
    happens when empty segments are skipped, and lags/dropped to say how far behind
    transcription had fallen and how much audio was discarded before each segment.
    """
    for position, item in enumerate(items):
        index = indices[position] if indices else position
        start = index * segment_seconds
        failed = isinstance(item, Failure)
        text = "" if failed else item
        cues = (Cue(start=float(start), end=float(start + 2), text=text),) if text.strip() else ()
        yield TranscriptSegment(
            index=index,
            text=text,
            start=float(start),
            end=float(start + segment_seconds),
            cues=cues,
            error=item.reason if failed else None,
            lag=lags[position] if position < len(lags) else 0.0,
            dropped=dropped[position] if position < len(dropped) else 0,
        )


class TestResolveOutputPath(unittest.TestCase):
    def test_explicit_arg_returned_as_is(self):
        with patch("sys2txt.__main__.ensure_output_dir") as mock_ensure_output_dir:
            result = _resolve_output_path("/tmp/my_output.txt")
        self.assertEqual(result, "/tmp/my_output.txt")
        mock_ensure_output_dir.assert_not_called()

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
        self.assertTrue(options.download_model)
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

    def test_lag_options_default_to_warning_only(self):
        options = _build_options(make_args())
        self.assertEqual(options.max_lag, 0.0)
        self.assertEqual(options.on_lag, "drop")

    def test_lag_options_are_copied_onto_options(self):
        options = _build_options(make_args(segment_seconds=8, max_lag=24.0, on_lag="fail"))
        self.assertEqual(options.max_lag, 24.0)
        self.assertEqual(options.on_lag, "fail")

    def test_negative_max_lag_is_rejected(self):
        with self.assertRaises(ValueError):
            _build_options(make_args(max_lag=-1.0))

    def test_max_lag_shorter_than_a_segment_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _build_options(make_args(segment_seconds=8, max_lag=3.0))
        self.assertIn("--max-lag", str(ctx.exception))

    def test_max_lag_equal_to_segment_length_is_accepted(self):
        self.assertEqual(_build_options(make_args(segment_seconds=8, max_lag=8.0)).max_lag, 8.0)

    def test_on_lag_without_max_lag_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            _build_options(make_args(on_lag="fail"))
        self.assertIn("--max-lag", str(ctx.exception))

    def test_output_format_defaults_to_txt(self):
        self.assertEqual(_build_options(make_args()).output_format, "txt")

    def test_output_format_is_copied_onto_options(self):
        self.assertEqual(_build_options(make_args(output_format="srt")).output_format, "srt")

    def test_warns_that_timestamps_add_nothing_to_a_timed_format(self):
        args = make_args(timestamps=True, output_format="vtt")
        with self.assertLogs("sys2txt.__main__", level="WARNING") as logs:
            _build_options(args)
        self.assertIn("--timestamps has no effect", logs.output[0])

    def test_no_warning_for_timestamps_with_plain_text(self):
        with self.assertRaises(AssertionError):
            with self.assertLogs("sys2txt.__main__", level="WARNING"):
                _build_options(make_args(timestamps=True, output_format="txt"))

    def test_warns_about_cpp_only_flags(self):
        args = make_args(engine="faster", model_path="/m.bin", whisper_cpp_path="/w", no_download=True)
        with self.assertLogs("sys2txt.__main__", level="WARNING") as logs:
            _build_options(args)
        self.assertEqual(len(logs.output), 3)

    def test_warns_that_vulkan_device_falls_back_to_cpu_on_non_cpp_engine(self):
        args = make_args(engine="faster", device="vulkan")
        with self.assertLogs("sys2txt.__main__", level="WARNING") as logs:
            _build_options(args)
        self.assertIn("--device vulkan", logs.output[0])

    def test_warns_that_gpu_device_falls_back_to_cpu_on_auto_engine(self):
        args = make_args(engine="auto", device="gpu")
        with self.assertLogs("sys2txt.__main__", level="WARNING") as logs:
            _build_options(args)
        self.assertIn("--device gpu", logs.output[0])

    def test_no_warning_for_vulkan_device_with_cpp_engine(self):
        with self.assertRaises(AssertionError):
            with self.assertLogs("sys2txt.__main__", level="WARNING"):
                _build_options(make_args(engine="cpp", device="vulkan"))

    def test_warns_that_cuda_device_is_not_a_whisper_cpp_device(self):
        args = make_args(engine="cpp", device="cuda")
        with self.assertLogs("sys2txt.__main__", level="WARNING") as logs:
            _build_options(args)
        self.assertIn("--device cuda", logs.output[0])


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

        mock_print.assert_called_once_with("hello world\n", end="")
        m.assert_called_once_with("/out/transcript.txt", "w", encoding="utf-8")
        m().write.assert_called_once_with("hello world\n")
        mock_logger.info.assert_called_once_with("Transcript saved to: %s", "/out/transcript.txt")


class TestCheckOutputWritable(unittest.TestCase):
    def test_missing_directory_raises_without_touching_disk(self):
        with self.assertRaisesRegex(RuntimeError, "directory does not exist"):
            _check_output_writable("/does/not/exist/transcript.txt")

    def test_writable_path_creates_and_leaves_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_file = os.path.join(tmp, "transcript.txt")
            _check_output_writable(output_file)
            self.assertTrue(os.path.isfile(output_file))
            self.assertEqual(os.path.getsize(output_file), 0)

    def test_unwritable_file_raises_runtime_error(self):
        with patch("builtins.open", side_effect=OSError("Permission denied")):
            with self.assertRaisesRegex(RuntimeError, "not writable"):
                _check_output_writable("/tmp/transcript.txt")


class TestArgumentParsing(unittest.TestCase):
    """Tests for CLI argument parsing."""

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_once_cues", return_value=Transcript())
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
    @patch("sys2txt.__main__.transcribe_file_cues", return_value=Transcript())
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_with_input_skips_recording(self, _res, _save, mock_trans, _src, _log):
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            with (
                patch("sys.argv", ["sys2txt", "once", "--input", audio.name]),
                patch("sys2txt.__main__.transcribe_once_cues") as mock_once,
            ):
                main()
            mock_once.assert_not_called()
            mock_trans.assert_called_once_with(audio.name, unittest.mock.ANY)

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_once_cues", return_value=Transcript())
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
        _res.assert_called_once_with("/tmp/my.txt", "txt")

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
                    "--max-lag",
                    "45",
                ],
            ):
                main()
        mock_live.assert_called_once()
        self.assertEqual(mock_live.call_args[0][0], "my.monitor")
        self.assertEqual(mock_live.call_args[1]["segment_seconds"], 15)
        self.assertEqual(mock_live.call_args[1]["max_lag"], 45.0)
        config = mock_live.call_args[0][1]
        self.assertEqual(config.model, "tiny")
        self.assertEqual(config.engine, "cpp")

    def test_missing_subcommand_exits(self):
        with patch("sys.argv", ["sys2txt"]):
            with self.assertRaises(SystemExit):
                main()

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_once_cues", side_effect=KeyboardInterrupt())
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

    def test_max_lag_shorter_than_segment(self):
        self._assert_usage_error(["sys2txt", "live", "--segment-seconds", "8", "--max-lag", "3"])

    def test_on_lag_without_max_lag(self):
        self._assert_usage_error(["sys2txt", "live", "--on-lag", "drop"])

    def test_unknown_output_format(self):
        self._assert_usage_error(["sys2txt", "once", "--format", "docx"])


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
    @patch("sys2txt.__main__.transcribe_once_cues", return_value=Transcript((Cue(0.0, 1.0, "hello world"),)))
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_records_then_transcribes(self, _res, mock_save, mock_once, _src, _log):
        with patch("sys.argv", ["sys2txt", "once"]):
            main()
        mock_once.assert_called_once()
        mock_save.assert_called_once_with("hello world", "/tmp/out.txt")

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_file_cues", return_value=Transcript((Cue(0.0, 1.0, "from file"),)))
    @patch("sys2txt.__main__._save_transcript")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/tmp/out.txt")
    def test_once_input_skips_recording(self, _res, mock_save, mock_trans, _src, _log):
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            with patch("sys.argv", ["sys2txt", "once", "--input", audio.name]):
                main()
            self.assertEqual(mock_trans.call_args[0][0], audio.name)
        mock_save.assert_called_once_with("from file", "/tmp/out.txt")

    @patch("sys2txt.__main__._configure_logging")
    @patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor")
    @patch("sys2txt.__main__.transcribe_once_cues")
    @patch("sys2txt.__main__._resolve_output_path", return_value="/does/not/exist/out.txt")
    def test_unwritable_output_fails_before_recording(self, _res, mock_once, _src, _log):
        with patch("sys.argv", ["sys2txt", "once"]):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)
        mock_once.assert_not_called()


class TestOnceOutputFormats(unittest.TestCase):
    """once mode renders the transcript in the format the user asked for."""

    def _run_once(self, argv, transcript):
        """Run the CLI in once mode against a canned transcript, returning the output file."""
        with tempfile.TemporaryDirectory() as tmp:
            output_file = os.path.join(tmp, "out")
            with (
                patch("sys2txt.__main__._configure_logging"),
                patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor"),
                patch("sys2txt.__main__._resolve_output_path", return_value=output_file),
                patch("sys2txt.__main__.transcribe_once_cues", return_value=transcript),
                patch("builtins.print") as mock_print,
                patch("sys.argv", argv),
            ):
                main()
            with open(output_file, encoding="utf-8") as f:
                written = f.read()
        return mock_print, written

    def setUp(self):
        self.transcript = Transcript(
            cues=(Cue(0.0, 1.5, "Hello"), Cue(1.5, 3.25, "world")),
            language="en",
        )

    def test_txt_is_unchanged_by_the_new_flag(self):
        _, written = self._run_once(["sys2txt", "once"], self.transcript)
        self.assertEqual(written, "Hello world\n")

    def test_srt(self):
        _, written = self._run_once(["sys2txt", "once", "--format", "srt"], self.transcript)
        self.assertEqual(
            written,
            "1\n00:00:00,000 --> 00:00:01,500\nHello\n\n2\n00:00:01,500 --> 00:00:03,250\nworld\n\n",
        )

    def test_vtt(self):
        _, written = self._run_once(["sys2txt", "once", "--format", "vtt"], self.transcript)
        self.assertTrue(written.startswith("WEBVTT\n\n"))
        self.assertIn("00:00:01.500 --> 00:00:03.250\nworld", written)

    def test_json_records_the_detected_language(self):
        _, written = self._run_once(["sys2txt", "once", "--format", "json"], self.transcript)
        document = json.loads(written)
        self.assertEqual(document["language"], "en")
        self.assertEqual(document["text"], "Hello world")

    def test_tsv(self):
        _, written = self._run_once(["sys2txt", "once", "--format", "tsv"], self.transcript)
        self.assertEqual(written, "start\tend\ttext\n0\t1500\tHello\n1500\t3250\tworld\n")

    def test_stdout_mirrors_the_file(self):
        mock_print, written = self._run_once(["sys2txt", "once", "--format", "srt"], self.transcript)
        mock_print.assert_called_once_with(written, end="")

    def test_generated_filename_takes_the_format_extension(self):
        with (
            patch("sys2txt.__main__.ensure_output_dir", return_value="/out"),
            patch("sys2txt.__main__.datetime") as mock_datetime,
        ):
            mock_datetime.now.return_value.strftime.return_value = "2024-01-01_00-00-00"
            self.assertEqual(_resolve_output_path(None, "srt"), os.path.join("/out", "2024-01-01_00-00-00.srt"))
            self.assertEqual(_resolve_output_path(None, "json"), os.path.join("/out", "2024-01-01_00-00-00.json"))


class TestLiveOutputFormats(unittest.TestCase):
    """live mode streams the transcript in the format the user asked for."""

    def _run_live(self, argv, segments):
        """Run the CLI in live mode against a canned segment stream, returning the output file."""
        with tempfile.TemporaryDirectory() as tmp:
            output_file = os.path.join(tmp, "out")
            with (
                patch("sys2txt.__main__._configure_logging"),
                patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor"),
                patch("sys2txt.__main__._resolve_output_path", return_value=output_file),
                patch("sys2txt.__main__.transcribe_live", return_value=segments),
                patch("builtins.print"),
                patch("sys.argv", argv),
            ):
                main()
            with open(output_file, encoding="utf-8") as f:
                written = f.read()
        return written

    def test_srt_numbers_cues_across_segments(self):
        written = self._run_live(
            ["sys2txt", "live", "--format", "srt"],
            live_segments("hello", "world"),
        )
        self.assertEqual(
            written,
            "1\n00:00:00,000 --> 00:00:02,000\nhello\n\n2\n00:00:08,000 --> 00:00:10,000\nworld\n\n",
        )

    def test_vtt_header_is_written_once_up_front(self):
        written = self._run_live(
            ["sys2txt", "live", "--format", "vtt"],
            live_segments("hello", "world"),
        )
        self.assertEqual(written.count("WEBVTT"), 1)
        self.assertTrue(written.startswith("WEBVTT\n\n"))

    def test_json_document_is_closed_when_capture_stops(self):
        written = self._run_live(
            ["sys2txt", "live", "--format", "json"],
            live_segments("hello", "world"),
        )
        document = json.loads(written)
        self.assertEqual([segment["start"] for segment in document["segments"]], [0.0, 8.0])

    def test_json_document_is_closed_on_keyboard_interrupt(self):
        """The whole JSON document is written from the footer, so Ctrl-C must still reach it."""

        def segments():
            yield from live_segments("hello")
            raise KeyboardInterrupt()

        written = self._run_live(["sys2txt", "live", "--format", "json"], segments())

        self.assertEqual(json.loads(written)["text"], "hello")

    def test_json_document_is_closed_on_silence_timeout(self):
        written = self._run_live(
            ["sys2txt", "live", "--format", "json", "--silence-timeout", "16"],
            live_segments("hello", "", "", "unreachable"),
        )
        self.assertEqual(json.loads(written)["text"], "hello")

    def test_silent_segments_produce_no_cues(self):
        written = self._run_live(
            ["sys2txt", "live", "--format", "srt"],
            live_segments("hello", "", "world"),
        )
        self.assertEqual(written.count("-->"), 2)

    def test_a_timed_format_replaces_rather_than_appends(self):
        """An SRT document cannot resume: cue numbering would restart mid-file."""
        with tempfile.TemporaryDirectory() as tmp:
            output_file = os.path.join(tmp, "out.srt")
            with open(output_file, "w", encoding="utf-8") as handle:
                handle.write("stale content\n")
            with (
                patch("sys2txt.__main__._configure_logging"),
                patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor"),
                patch("sys2txt.__main__._resolve_output_path", return_value=output_file),
                patch("sys2txt.__main__.transcribe_live", return_value=live_segments("hello")),
                patch("builtins.print"),
                patch("sys.argv", ["sys2txt", "live", "--format", "srt"]),
            ):
                main()
            with open(output_file, encoding="utf-8") as f:
                self.assertNotIn("stale content", f.read())


class LiveRun:
    """Runs the CLI in live mode against a canned segment stream."""

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


class TestModeDispatchLive(LiveRun, unittest.TestCase):
    """Tests for live mode consumption of the transcript stream."""

    def test_unwritable_output_fails_before_capture(self):
        with (
            patch("sys2txt.__main__._configure_logging"),
            patch("sys2txt.__main__.get_default_monitor_source", return_value="default.monitor"),
            patch("sys2txt.__main__._resolve_output_path", return_value="/does/not/exist/out.txt"),
            patch("sys2txt.__main__.transcribe_live") as mock_live,
            patch("sys.argv", ["sys2txt", "live"]),
        ):
            with self.assertRaises(SystemExit) as ctx:
                main()
        self.assertEqual(ctx.exception.code, 1)
        mock_live.assert_not_called()

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


class TestLiveBackpressure(LiveRun, unittest.TestCase):
    """Tests for what live mode does when transcription cannot keep up with recording."""

    def test_no_cap_is_passed_by_default(self):
        mock_live, _, _ = self._run_live(["sys2txt", "live"], live_segments("hello"))
        self.assertEqual(mock_live.call_args[1]["max_lag"], 0.0)

    def test_drop_policy_hands_the_cap_to_the_recorder(self):
        mock_live, _, _ = self._run_live(
            ["sys2txt", "live", "--max-lag", "24"],
            live_segments("hello"),
        )
        self.assertEqual(mock_live.call_args[1]["max_lag"], 24.0)

    def test_fail_policy_keeps_every_segment(self):
        """Failing is a decision about the run, so nothing is dropped on the way to it."""
        mock_live, _, _ = self._run_live(
            ["sys2txt", "live", "--max-lag", "24", "--on-lag", "fail"],
            live_segments("hello", lags=(8.0,)),
        )
        self.assertEqual(mock_live.call_args[1]["max_lag"], 0.0)

    def test_fail_policy_stops_once_the_lag_is_past_the_maximum(self):
        segments = live_segments("hello", "behind", "should never be reached", lags=(0.0, 32.0))
        with self.assertLogs("sys2txt.__main__", level="ERROR") as logs:
            _, mock_print, written = self._run_live(
                ["sys2txt", "live", "--max-lag", "24", "--on-lag", "fail"],
                segments,
            )

        self.assertEqual(self.exit_code, 1)
        self.assertEqual(mock_print.call_count, 2)
        self.assertIn("32s behind", logs.output[0])
        self.assertIn("--max-lag of 24s", logs.output[0])
        # The transcript produced before giving up is still saved
        self.assertEqual(written, "hello\nbehind\n")

    def test_lag_within_the_maximum_does_not_stop_the_run(self):
        _, mock_print, _ = self._run_live(
            ["sys2txt", "live", "--max-lag", "24", "--on-lag", "fail"],
            live_segments("hello", "world", lags=(8.0, 24.0)),
        )
        self.assertEqual(mock_print.call_count, 2)
        self.assertEqual(self.exit_code, 0)

    def test_dropped_audio_does_not_count_as_silence(self):
        """A hole in the recording says nothing about whether anyone was speaking."""
        segments = live_segments("", "", "", "should never be reached", dropped=(0, 2, 0, 0))
        _, mock_print, _ = self._run_live(
            ["sys2txt", "live", "--max-lag", "24", "--silence-timeout", "16"],
            segments,
        )
        # Without the reset the second segment would already have reached the timeout
        self.assertEqual(mock_print.call_count, 3)
        self.assertEqual(self.exit_code, 0)

    def test_dropped_audio_is_not_a_transcription_failure(self):
        """Dropping is a deliberate policy, so it never trips the consecutive-failure limit."""
        segments = live_segments("", "", "", "", "hello", dropped=(1, 1, 1, 1, 0))
        _, mock_print, written = self._run_live(
            ["sys2txt", "live", "--max-lag", "16"],
            segments,
        )
        self.assertEqual(mock_print.call_count, 5)
        self.assertEqual(written, "\n\n\n\n" + "hello\n")
        self.assertEqual(self.exit_code, 0)


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
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SYS2TXT_LOG_LEVEL", None)
            _configure_logging(verbose=True, quiet=False)
        self.assertEqual(logging.getLogger().level, logging.DEBUG)

    def test_quiet_sets_warning(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SYS2TXT_LOG_LEVEL", None)
            _configure_logging(verbose=False, quiet=True)
        self.assertEqual(logging.getLogger().level, logging.WARNING)

    def test_default_sets_warning(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SYS2TXT_LOG_LEVEL", None)
            _configure_logging(verbose=False, quiet=False)
        self.assertEqual(logging.getLogger().level, logging.WARNING)

    def test_explicit_flags_override_log_level_env(self):
        with patch.dict(os.environ, {"SYS2TXT_LOG_LEVEL": "ERROR"}):
            _configure_logging(verbose=True, quiet=False)
        self.assertEqual(logging.getLogger().level, logging.DEBUG)

    def test_log_level_env_used_when_no_flags(self):
        with patch.dict(os.environ, {"SYS2TXT_LOG_LEVEL": "ERROR"}):
            _configure_logging(verbose=False, quiet=False)
        self.assertEqual(logging.getLogger().level, logging.ERROR)

    def test_log_level_env_invalid_value_falls_back_to_default(self):
        with patch.dict(os.environ, {"SYS2TXT_LOG_LEVEL": "RAISEEXCEPTIONS"}):
            _configure_logging(verbose=False, quiet=False)
        self.assertEqual(logging.getLogger().level, logging.WARNING)

    def test_configure_logging_does_not_duplicate_handlers(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SYS2TXT_LOG_LEVEL", None)
            _configure_logging(verbose=False, quiet=False)
            _configure_logging(verbose=False, quiet=False)
        self.assertEqual(len(logging.getLogger().handlers), 1)


if __name__ == "__main__":
    unittest.main()
