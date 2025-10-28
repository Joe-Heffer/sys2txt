"""Tests for sys2txt.utils module."""

import unittest
from unittest.mock import patch

from sys2txt.utils import which


class TestWhich(unittest.TestCase):
    """Tests for the which() function."""

    @patch("sys2txt.utils.shutil.which")
    def test_which_command_exists(self, mock_which):
        """Test which() returns path when command exists."""
        mock_which.return_value = "/usr/bin/python3"
        result = which("python3")
        self.assertEqual(result, "/usr/bin/python3")
        mock_which.assert_called_once_with("python3")

    @patch("sys2txt.utils.shutil.which")
    def test_which_command_not_found(self, mock_which):
        """Test which() raises RuntimeError when command not found."""
        mock_which.return_value = None
        with self.assertRaises(RuntimeError) as cm:
            which("nonexistent_command")
        self.assertIn("nonexistent_command", str(cm.exception))
        self.assertIn("not found", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
