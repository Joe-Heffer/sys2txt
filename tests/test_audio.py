"""Tests for sys2txt.audio module."""

import os
import signal
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sys2txt.audio import AudioSegment, iter_audio_segments, record_once


class TestRecordOnce(unittest.TestCase):
    """Tests for the record_once() function."""

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    def test_record_once_with_duration(self, mock_popen, mock_which):
        """Test record_once() with fixed duration."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.wait.return_value = None
        mock_popen.return_value = mock_proc

        record_once("test.monitor", "/tmp/test.wav", 30)

        mock_which.assert_called_once_with("ffmpeg")
        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        self.assertIn("/usr/bin/ffmpeg", args)
        self.assertIn("test.monitor", args)
        self.assertIn("/tmp/test.wav", args)
        self.assertIn("-t", args)
        self.assertIn("30", args)
        mock_proc.wait.assert_called_once()

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    def test_record_once_without_duration(self, mock_popen, mock_which):
        """Test record_once() without duration (Ctrl-C to stop)."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.wait.return_value = None
        mock_popen.return_value = mock_proc

        record_once("test.monitor", "/tmp/test.wav")

        args = mock_popen.call_args[0][0]
        self.assertNotIn("-t", args)
        mock_proc.wait.assert_called_once()

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    def test_record_once_uses_default_sample_rate_and_channels(self, mock_popen, mock_which):
        """Sample rate and channels default to the Whisper-compatible constants."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_popen.return_value = MagicMock()

        record_once("test.monitor", "/tmp/test.wav")

        args = mock_popen.call_args[0][0]
        self.assertEqual(args[args.index("-ar") + 1], "16000")
        self.assertEqual(args[args.index("-ac") + 1], "1")

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    def test_record_once_keyboard_interrupt(self, mock_popen, mock_which):
        """Test record_once() handles KeyboardInterrupt gracefully."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = [KeyboardInterrupt(), None]
        mock_popen.return_value = mock_proc

        record_once("test.monitor", "/tmp/test.wav")

        mock_proc.send_signal.assert_called_once_with(signal.SIGINT)
        self.assertEqual(mock_proc.wait.call_count, 2)


class TestIterAudioSegments(unittest.TestCase):
    """Tests for the iter_audio_segments() generator."""

    def _ffmpeg_proc(self, poll_results=None, poll_return=None):
        """Build a mock ffmpeg process."""
        proc = MagicMock()
        if poll_results is not None:
            proc.poll.side_effect = poll_results
        else:
            proc.poll.return_value = poll_return
        proc.stdin = MagicMock()
        proc.wait.return_value = None
        return proc

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    @patch("sys2txt.audio.os.path.getsize")
    def test_yields_finalized_segments_in_order(self, mock_getsize, mock_listdir, _sleep, mock_popen, mock_which):
        """Segments are yielded in order, the newest deferred until ffmpeg exits."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        # Three loop polls plus one from the shutdown helper
        mock_popen.return_value = self._ffmpeg_proc(poll_results=[None, None, 0, 0])
        mock_listdir.side_effect = [
            [],
            ["seg_00000.wav"],  # only one file: still being written
            ["seg_00000.wav", "seg_00001.wav"],  # seg_00000 is finalized
            ["seg_00000.wav", "seg_00001.wav"],  # flush path picks up seg_00001
        ]
        mock_getsize.return_value = 1024

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segments = list(iter_audio_segments("test.monitor", 8))

        self.assertEqual([s.index for s in segments], [0, 1])
        self.assertTrue(segments[0].path.endswith("seg_00000.wav"))
        self.assertTrue(segments[1].path.endswith("seg_00001.wav"))
        self.assertIsInstance(segments[0], AudioSegment)

        args = mock_popen.call_args[0][0]
        self.assertIn("/usr/bin/ffmpeg", args)
        self.assertIn("test.monitor", args)
        self.assertEqual(args[args.index("-segment_time") + 1], "8")

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    def test_skips_empty_segments_but_keeps_index_on_the_timeline(self, _sleep, mock_popen, mock_which):
        """A segment holding no audio is skipped, but still consumes its index."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_popen.return_value = self._ffmpeg_proc(poll_results=[None, 0, 0])

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "seg_00000.wav"), "wb") as f:
                f.write(b"x" * 32)  # below MIN_SEGMENT_BYTES
            with open(os.path.join(tmpdir, "seg_00001.wav"), "wb") as f:
                f.write(b"x" * 1024)

            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segments = list(iter_audio_segments("test.monitor", 8))

        self.assertEqual([s.index for s in segments], [1])

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    def test_no_segments_when_all_files_are_empty(self, _sleep, mock_popen, mock_which):
        """Nothing is yielded when every segment file is header-only."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_popen.return_value = self._ffmpeg_proc(poll_results=[0, 0])

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "seg_00000.wav"), "wb") as f:
                f.write(b"x" * 32)

            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segments = list(iter_audio_segments("test.monitor", 8))

        self.assertEqual(segments, [])

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    @patch("sys2txt.audio.os.path.getsize")
    def test_closing_the_generator_stops_ffmpeg(self, mock_getsize, mock_listdir, _sleep, mock_popen, mock_which):
        """A consumer that stops iterating shuts ffmpeg down gracefully."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        proc = self._ffmpeg_proc(poll_return=None)  # ffmpeg keeps running
        mock_popen.return_value = proc
        mock_listdir.return_value = ["seg_00000.wav", "seg_00001.wav"]
        mock_getsize.return_value = 1024

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segments = iter_audio_segments("test.monitor", 8)
                first = next(segments)
                segments.close()

        self.assertEqual(first.index, 0)
        proc.stdin.write.assert_called_once_with(b"q")
        proc.stdin.flush.assert_called_once()
        proc.stdin.close.assert_called_once()
        proc.wait.assert_called()

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    @patch("sys2txt.audio.os.path.getsize")
    def test_no_quit_sent_when_ffmpeg_exits_on_its_own(
        self, mock_getsize, mock_listdir, _sleep, mock_popen, mock_which
    ):
        """ffmpeg that has already exited is not asked to quit again."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        proc = self._ffmpeg_proc(poll_return=0)
        mock_popen.return_value = proc
        mock_listdir.return_value = ["seg_00000.wav"]
        mock_getsize.return_value = 1024

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segments = list(iter_audio_segments("test.monitor", 8))

        self.assertEqual([s.index for s in segments], [0])
        proc.stdin.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
