"""Utility functions."""

import shutil


def which(cmd: str) -> str:
    """Find command in PATH or raise RuntimeError if not found."""
    path = shutil.which(cmd)
    if not path:
        raise RuntimeError(f"Required command not found: {cmd}. Please install it and try again.")
    return path
