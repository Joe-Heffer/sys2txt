"""Tests for sys2txt.audio module."""

import os
import signal
import tempfile
import threading
import unittest
from itertools import chain, repeat
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


def _write_segments(directory, count, size=1024):
    """Fill a directory with finalized segment files, as ffmpeg would leave them."""
    for i in range(count):
        with open(os.path.join(directory, f"seg_{i:05d}.wav"), "wb") as f:
            f.write(b"x" * size)


class TestIterAudioSegments(unittest.TestCase):
    """Tests for the iter_audio_segments() generator."""

    def _ffmpeg_proc(self, poll_results=None, poll_return=None, stderr_lines=()):
        """Build a mock ffmpeg process, whose last poll result repeats for as long as asked."""
        proc = MagicMock()
        if poll_results is not None:
            proc.poll.side_effect = chain(poll_results, repeat(poll_results[-1]))
        else:
            proc.poll.return_value = poll_return
        proc.stdin = MagicMock()
        proc.stderr = iter(stderr_lines)
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
        mock_popen.return_value = self._ffmpeg_proc(poll_results=[None, None, 0])
        listings = [
            [],
            ["seg_00000.wav"],  # only one file: still being written
            ["seg_00000.wav", "seg_00001.wav"],  # seg_00000 is finalized
        ]
        mock_listdir.side_effect = chain(listings, repeat(listings[-1]))
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
        mock_popen.return_value = self._ffmpeg_proc(poll_return=0)

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
        mock_popen.return_value = self._ffmpeg_proc(poll_return=0)

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

    @patch("sys2txt.audio.which", return_value="/usr/bin/ffmpeg")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    def test_lag_reports_the_audio_waiting_behind_a_segment(self, _sleep, mock_popen, _which):
        """Lag is the recorded audio still queued, so it falls to zero as the queue drains."""
        mock_popen.return_value = self._ffmpeg_proc(poll_return=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            _write_segments(tmpdir, 3)
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segments = list(iter_audio_segments("test.monitor", 8))

        self.assertEqual([s.lag for s in segments], [16.0, 8.0, 0.0])
        self.assertEqual([s.dropped for s in segments], [0, 0, 0])

    @patch("sys2txt.audio.which", return_value="/usr/bin/ffmpeg")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    def test_backlog_is_kept_when_no_maximum_lag_is_given(self, _sleep, mock_popen, _which):
        """Without a cap, a backlog is handed over in full however far behind it is."""
        mock_popen.return_value = self._ffmpeg_proc(poll_return=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            _write_segments(tmpdir, 5)
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segments = list(iter_audio_segments("test.monitor", 8))

        self.assertEqual([s.index for s in segments], [0, 1, 2, 3, 4])

    @patch("sys2txt.audio.which", return_value="/usr/bin/ffmpeg")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    def test_oldest_segments_are_dropped_to_stay_within_max_lag(self, _sleep, mock_popen, _which):
        """The newest audio is kept, and the dropped indices are still consumed."""
        mock_popen.return_value = self._ffmpeg_proc(poll_return=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            _write_segments(tmpdir, 5)
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                with self.assertLogs("sys2txt.audio", level="WARNING") as logs:
                    segments = list(iter_audio_segments("test.monitor", 8, max_lag=16))
            remaining = os.listdir(tmpdir)

        # Indices survive the drop, so index * segment_seconds still lands on the timeline
        self.assertEqual([s.index for s in segments], [3, 4])
        self.assertEqual([s.dropped for s in segments], [3, 0])
        self.assertIn("dropped 3 segment(s), 24s of audio", logs.output[0])
        # Dropped segments are deleted rather than left filling the temporary directory
        self.assertEqual(remaining, [])

    @patch("sys2txt.audio.which", return_value="/usr/bin/ffmpeg")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    def test_segment_file_is_removed_once_the_consumer_moves_on(self, _sleep, mock_popen, _which):
        """The temporary directory holds the backlog, not every segment of the session."""
        mock_popen.return_value = self._ffmpeg_proc(poll_return=0)

        with tempfile.TemporaryDirectory() as tmpdir:
            _write_segments(tmpdir, 2)
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segments = iter_audio_segments("test.monitor", 8)
                first = next(segments)
                self.assertTrue(os.path.exists(first.path))
                next(segments)
                # Asking for the next segment says the consumer is done with the last one
                self.assertFalse(os.path.exists(first.path))
                segments.close()

    @patch("sys2txt.audio.which", return_value="/usr/bin/ffmpeg")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    def test_ffmpeg_stderr_is_drained_and_logged(self, _sleep, mock_popen, _which):
        """ffmpeg's stderr is read in the background and logged, rather than left to fill up."""
        proc = self._ffmpeg_proc(poll_return=0, stderr_lines=[b"Error: something bad\n"])
        mock_popen.return_value = proc

        with tempfile.TemporaryDirectory() as tmpdir:
            _write_segments(tmpdir, 1)
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                with self.assertLogs("sys2txt.audio", level="WARNING") as logs:
                    list(iter_audio_segments("test.monitor", 8))
                    # The drainer runs on its own thread; give it a moment to log.
                    for thread in threading.enumerate():
                        if thread is not threading.current_thread() and thread.daemon:
                            thread.join(timeout=1)

        self.assertTrue(any("ffmpeg: Error: something bad" in line for line in logs.output))


if __name__ == "__main__":
    unittest.main()
