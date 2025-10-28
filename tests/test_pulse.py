"""Tests for sys2txt.pulse module."""

import unittest
from unittest.mock import patch

from sys2txt.pulse import get_default_monitor_source, list_pulse_sources, run_command


class TestRunCommand(unittest.TestCase):
    """Tests for the run_command() function."""

    @patch("sys2txt.pulse.subprocess.Popen")
    def test_run_command_success(self, mock_popen):
        """Test run_command() with successful command execution."""
        mock_proc = mock_popen.return_value
        mock_proc.communicate.return_value = ("output", "")
        mock_proc.returncode = 0

        code, out, err = run_command(["echo", "test"])

        self.assertEqual(code, 0)
        self.assertEqual(out, "output")
        self.assertEqual(err, "")

    @patch("sys2txt.pulse.subprocess.Popen")
    def test_run_command_failure(self, mock_popen):
        """Test run_command() with failed command execution."""
        mock_proc = mock_popen.return_value
        mock_proc.communicate.return_value = ("", "error")
        mock_proc.returncode = 1

        code, out, err = run_command(["false"])

        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertEqual(err, "error")


class TestListPulseSources(unittest.TestCase):
    """Tests for the list_pulse_sources() function."""

    @patch("sys2txt.pulse.run_command")
    def test_list_pulse_sources_success(self, mock_run):
        """Test list_pulse_sources() with valid pactl output."""
        mock_run.return_value = (
            0,
            "0\talsa_output.monitor\tmodule-alsa\ts16le 2ch 48000Hz\tRUNNING\n"
            "1\tpulse_input\tmodule-pulse\ts16le 2ch 44100Hz\tIDLE\n",
            "",
        )

        sources = list_pulse_sources()

        self.assertEqual(len(sources), 2)
        self.assertEqual(sources[0], ("alsa_output.monitor", "alsa_output.monitor"))
        self.assertEqual(sources[1], ("pulse_input", "pulse_input"))

    @patch("sys2txt.pulse.run_command")
    def test_list_pulse_sources_failure(self, mock_run):
        """Test list_pulse_sources() when pactl command fails."""
        mock_run.return_value = (1, "", "error")

        sources = list_pulse_sources()

        self.assertEqual(sources, [])

    @patch("sys2txt.pulse.run_command")
    def test_list_pulse_sources_no_pactl(self, mock_run):
        """Test list_pulse_sources() when pactl is not installed."""
        mock_run.side_effect = FileNotFoundError()

        sources = list_pulse_sources()

        self.assertEqual(sources, [])


class TestGetDefaultMonitorSource(unittest.TestCase):
    """Tests for the get_default_monitor_source() function."""

    @patch("sys2txt.pulse.list_pulse_sources")
    @patch("sys2txt.pulse.run_command")
    def test_get_default_monitor_source_success(self, mock_run, mock_list):
        """Test get_default_monitor_source() finds default sink monitor."""
        mock_run.return_value = (0, "alsa_output.pci\n", "")
        mock_list.return_value = [
            ("alsa_output.pci.monitor", "alsa_output.pci.monitor"),
            ("other.monitor", "other.monitor"),
        ]

        source = get_default_monitor_source()

        self.assertEqual(source, "alsa_output.pci.monitor")

    @patch("sys2txt.pulse.list_pulse_sources")
    @patch("sys2txt.pulse.run_command")
    def test_get_default_monitor_source_fallback_to_first_monitor(self, mock_run, mock_list):
        """Test get_default_monitor_source() falls back to first .monitor source."""
        mock_run.return_value = (1, "", "error")
        mock_list.return_value = [
            ("input_device", "input_device"),
            ("first.monitor", "first.monitor"),
            ("second.monitor", "second.monitor"),
        ]

        source = get_default_monitor_source()

        self.assertEqual(source, "first.monitor")

    @patch("sys2txt.pulse.list_pulse_sources")
    @patch("sys2txt.pulse.run_command")
    def test_get_default_monitor_source_fallback_to_default(self, mock_run, mock_list):
        """Test get_default_monitor_source() falls back to 'default'."""
        mock_run.return_value = (1, "", "error")
        mock_list.return_value = [("input_device", "input_device")]

        source = get_default_monitor_source()

        self.assertEqual(source, "default")

    @patch("sys2txt.pulse.list_pulse_sources")
    @patch("sys2txt.pulse.run_command")
    def test_get_default_monitor_source_exception(self, mock_run, mock_list):
        """Test get_default_monitor_source() handles exceptions gracefully."""
        mock_run.side_effect = Exception("Unexpected error")
        mock_list.return_value = []

        source = get_default_monitor_source()

        self.assertEqual(source, "default")


if __name__ == "__main__":
    unittest.main()
