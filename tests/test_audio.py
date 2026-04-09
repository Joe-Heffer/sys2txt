"""Tests for sys2txt.audio module."""

import os
import signal
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from sys2txt.audio import record_once, segment_and_transcribe_live


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

        record_once("test.monitor", "/tmp/test.wav", 16000, 1, 30)

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

        record_once("test.monitor", "/tmp/test.wav", 16000, 1, None)

        args = mock_popen.call_args[0][0]
        self.assertNotIn("-t", args)
        mock_proc.wait.assert_called_once()

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    def test_record_once_keyboard_interrupt(self, mock_popen, mock_which):
        """Test record_once() handles KeyboardInterrupt gracefully."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.wait.side_effect = [KeyboardInterrupt(), None]
        mock_popen.return_value = mock_proc

        record_once("test.monitor", "/tmp/test.wav", 16000, 1, None)

        mock_proc.send_signal.assert_called_once_with(signal.SIGINT)
        self.assertEqual(mock_proc.wait.call_count, 2)


class TestSegmentAndTranscribeLive(unittest.TestCase):
    """Tests for the segment_and_transcribe_live() function."""

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    @patch("sys2txt.audio.os.path.getsize")
    def test_segment_and_transcribe_live_basic(self, mock_getsize, mock_listdir, mock_sleep, mock_popen, mock_which):
        """Test segment_and_transcribe_live() basic functionality."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, None, 0]  # ffmpeg exits after 3 checks
        mock_proc.stdin = MagicMock()
        mock_popen.return_value = mock_proc

        # Simulate two segments being created. The flush-path listdir call must also
        # return both files so the second segment is picked up after ffmpeg exits.
        mock_listdir.side_effect = [
            [],
            ["seg_00000.wav"],
            ["seg_00000.wav", "seg_00001.wav"],
            ["seg_00000.wav", "seg_00001.wav"],  # flush path: seg_00001 not yet processed
        ]
        mock_getsize.return_value = 1024  # Files have content

        transcribe_callback = MagicMock(side_effect=["transcript 1", "transcript 2"])

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir

                segment_and_transcribe_live("test.monitor", 16000, 1, 8, transcribe_callback, None)

        # Verify ffmpeg was called with correct args
        mock_which.assert_called_once_with("ffmpeg")
        args = mock_popen.call_args[0][0]
        self.assertIn("/usr/bin/ffmpeg", args)
        self.assertIn("test.monitor", args)
        self.assertIn("-segment_time", args)
        self.assertIn("8", args)

        # Verify transcribe callback was called for both segments
        self.assertEqual(transcribe_callback.call_count, 2)

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    def test_segment_and_transcribe_live_with_output(self, mock_sleep, mock_popen, mock_which):
        """Test segment_and_transcribe_live() writes to output file."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]
        mock_proc.stdin = MagicMock()
        mock_popen.return_value = mock_proc

        transcribe_callback = MagicMock(return_value="test transcript")

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            output_path = f.name

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                # Create a test segment file
                seg_file = os.path.join(tmpdir, "seg_00000.wav")
                with open(seg_file, "wb") as f:
                    f.write(b"x" * 1024)  # Create a file with content

                with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                    mock_tmpdir.return_value.__enter__.return_value = tmpdir

                    segment_and_transcribe_live("test.monitor", 16000, 1, 8, transcribe_callback, output_path)

            # Verify output was written
            with open(output_path, "r") as f:
                content = f.read()
                self.assertIn("test transcript", content)
        finally:
            os.unlink(output_path)

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    def test_segment_and_transcribe_live_keyboard_interrupt(self, mock_listdir, mock_sleep, mock_popen, mock_which):
        """Test segment_and_transcribe_live() handles KeyboardInterrupt gracefully."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.stdin = MagicMock()
        mock_proc.wait.return_value = None
        mock_popen.return_value = mock_proc

        # Simulate KeyboardInterrupt during processing
        mock_listdir.side_effect = KeyboardInterrupt()

        transcribe_callback = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir

                segment_and_transcribe_live("test.monitor", 16000, 1, 8, transcribe_callback, None)

        # Verify graceful shutdown - 'q' sent to ffmpeg stdin
        mock_proc.stdin.write.assert_called_once_with(b"q")
        mock_proc.stdin.flush.assert_called_once()
        mock_proc.stdin.close.assert_called_once()
        mock_proc.wait.assert_called()

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    def test_segment_and_transcribe_live_skips_small_files(self, mock_sleep, mock_popen, mock_which):
        """Test segment_and_transcribe_live() skips files smaller than 64 bytes."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, 0]
        mock_proc.stdin = MagicMock()
        mock_popen.return_value = mock_proc

        transcribe_callback = MagicMock()

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a small test segment file (less than 64 bytes)
            seg_file = os.path.join(tmpdir, "seg_00000.wav")
            with open(seg_file, "wb") as f:
                f.write(b"x" * 32)  # File too small

            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir

                segment_and_transcribe_live("test.monitor", 16000, 1, 8, transcribe_callback, None)

        # Verify callback was NOT called for small file
        transcribe_callback.assert_not_called()

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    @patch("sys2txt.audio.os.path.getsize")
    def test_live_skips_last_segment_while_ffmpeg_running(
        self, mock_getsize, mock_listdir, mock_sleep, mock_popen, mock_which
    ):
        """While ffmpeg is running, the newest segment (still being written) is not transcribed."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        # ffmpeg running on first poll, exits on second
        mock_proc.poll.side_effect = [None, 0]
        mock_proc.stdin = MagicMock()
        mock_popen.return_value = mock_proc

        mock_listdir.side_effect = [
            ["seg_00000.wav", "seg_00001.wav"],  # live iter 1: seg_00000 safe, seg_00001 skipped
            ["seg_00000.wav", "seg_00001.wav"],  # live iter 2: nothing new safe
            ["seg_00000.wav", "seg_00001.wav"],  # flush path: seg_00001 now processed
        ]
        mock_getsize.return_value = 1024

        transcribe_callback = MagicMock(side_effect=["transcript 0", "transcript 1"])

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segment_and_transcribe_live("test.monitor", 16000, 1, 8, transcribe_callback, None)

        # Both segments transcribed: seg_00000 in live loop, seg_00001 in flush path
        self.assertEqual(transcribe_callback.call_count, 2)
        first_call_path = transcribe_callback.call_args_list[0][0][0]
        second_call_path = transcribe_callback.call_args_list[1][0][0]
        self.assertIn("seg_00000", first_call_path)
        self.assertIn("seg_00001", second_call_path)

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    @patch("sys2txt.audio.os.path.getsize")
    def test_live_processes_last_segment_in_flush_path(
        self, mock_getsize, mock_listdir, mock_sleep, mock_popen, mock_which
    ):
        """After ffmpeg exits, the last segment (deferred during live polling) is transcribed."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        # ffmpeg exits immediately on first poll; single file only visible during flush
        mock_proc.poll.side_effect = [0]
        mock_proc.stdin = MagicMock()
        mock_popen.return_value = mock_proc

        mock_listdir.side_effect = [
            ["seg_00000.wav"],  # live iter 1: one file, not safe (it's the active one) → skipped
            ["seg_00000.wav"],  # flush path: ffmpeg closed it, now process it
        ]
        mock_getsize.return_value = 1024

        transcribe_callback = MagicMock(return_value="transcript 0")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segment_and_transcribe_live("test.monitor", 16000, 1, 8, transcribe_callback, None)

        # Segment must have been transcribed (in the flush path, not the live loop)
        transcribe_callback.assert_called_once()
        call_path = transcribe_callback.call_args_list[0][0][0]
        self.assertIn("seg_00000", call_path)

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    @patch("sys2txt.audio.os.path.getsize")
    def test_silence_timeout_triggers_shutdown(self, mock_getsize, mock_listdir, mock_sleep, mock_popen, mock_which):
        """Test that silence_timeout stops live mode after enough consecutive silent segments."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        # ffmpeg keeps running; silence timeout should stop it
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.wait.return_value = None
        mock_popen.return_value = mock_proc

        # Two segments processed, both silent — with segment_seconds=8 and silence_timeout=16
        mock_listdir.side_effect = [
            ["seg_00000.wav", "seg_00001.wav"],  # seg_00000 safe
            ["seg_00000.wav", "seg_00001.wav", "seg_00002.wav"],  # seg_00001 safe
        ]
        mock_getsize.return_value = 1024

        transcribe_callback = MagicMock(return_value="")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segment_and_transcribe_live("test.monitor", 16000, 1, 8, transcribe_callback, None, silence_timeout=16)

        # Verify graceful shutdown — 'q' sent to ffmpeg
        mock_proc.stdin.write.assert_called_once_with(b"q")
        mock_proc.stdin.flush.assert_called_once()
        mock_proc.stdin.close.assert_called_once()

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    @patch("sys2txt.audio.os.path.getsize")
    def test_silence_timeout_resets_on_speech(self, mock_getsize, mock_listdir, mock_sleep, mock_popen, mock_which):
        """Test that the silence counter resets when speech is detected."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        # ffmpeg exits after processing all segments
        mock_proc.poll.side_effect = [None, None, None, 0]
        mock_proc.stdin = MagicMock()
        mock_popen.return_value = mock_proc

        # Three segments: silent, speech, silent — should NOT trigger timeout at 16s
        all_files = ["seg_00000.wav", "seg_00001.wav", "seg_00002.wav", "seg_00003.wav"]
        mock_listdir.side_effect = [
            all_files[:2],  # iter 1: seg_00000 safe (silent)
            all_files[:3],  # iter 2: seg_00001 safe (speech)
            all_files[:4],  # iter 3: seg_00002 safe (silent)
            all_files[:4],  # iter 4: nothing new safe, poll returns 0
            all_files[:4],  # flush path: seg_00003
        ]
        mock_getsize.return_value = 1024

        transcribe_callback = MagicMock(side_effect=["", "hello world", "", ""])

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segment_and_transcribe_live("test.monitor", 16000, 1, 8, transcribe_callback, None, silence_timeout=16)

        # All 4 segments were transcribed (no premature shutdown)
        self.assertEqual(transcribe_callback.call_count, 4)
        # ffmpeg was NOT sent 'q' — it exited naturally
        mock_proc.stdin.write.assert_not_called()

    @patch("sys2txt.audio.which")
    @patch("sys2txt.audio.subprocess.Popen")
    @patch("sys2txt.audio.time.sleep")
    @patch("sys2txt.audio.os.listdir")
    @patch("sys2txt.audio.os.path.getsize")
    def test_silence_timeout_disabled_by_default(self, mock_getsize, mock_listdir, mock_sleep, mock_popen, mock_which):
        """Test that silence_timeout=0 (default) does not trigger auto-stop."""
        mock_which.return_value = "/usr/bin/ffmpeg"
        mock_proc = MagicMock()
        mock_proc.poll.side_effect = [None, None, 0]
        mock_proc.stdin = MagicMock()
        mock_popen.return_value = mock_proc

        # Three silent segments — should NOT trigger timeout when disabled
        all_files = ["seg_00000.wav", "seg_00001.wav", "seg_00002.wav"]
        mock_listdir.side_effect = [
            all_files[:2],  # iter 1: seg_00000 safe
            all_files[:3],  # iter 2: seg_00001 safe
            all_files[:3],  # iter 3: nothing new, poll returns 0
            all_files[:3],  # flush: seg_00002
        ]
        mock_getsize.return_value = 1024

        transcribe_callback = MagicMock(return_value="")

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("sys2txt.audio.tempfile.TemporaryDirectory") as mock_tmpdir:
                mock_tmpdir.return_value.__enter__.return_value = tmpdir
                segment_and_transcribe_live("test.monitor", 16000, 1, 8, transcribe_callback, None, silence_timeout=0)

        # All segments processed, no premature shutdown
        self.assertEqual(transcribe_callback.call_count, 3)
        mock_proc.stdin.write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
