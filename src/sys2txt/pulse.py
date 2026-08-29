"""PulseAudio/PipeWire integration for source enumeration and selection."""

import logging
import subprocess
from typing import List, Tuple

logger = logging.getLogger(__name__)


def run_command(cmd: List[str]) -> Tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out, err = p.communicate()
    return p.returncode, out, err


def list_pulse_sources() -> List[Tuple[str, str]]:
    """Return list of (name, description) for PulseAudio sources."""
    try:
        code, out, err = run_command(["pactl", "list", "short", "sources"])
        if code != 0:
            logger.warning("pactl exited with code %d: %s", code, err.strip())
            return []
        items: List[Tuple[str, str]] = []
        for line in out.splitlines():
            # Format: index\tname\tmodule\tsampleSpec\tstate
            parts = line.split("\t")
            if len(parts) >= 2:
                name = parts[1]
                items.append((name, name))
        return items
    except FileNotFoundError:
        logger.warning("pactl not found. Is PulseAudio/PipeWire installed?")
        return []


def get_default_monitor_source() -> str:
    """Pick the default sink's .monitor if available; otherwise the first *.monitor source; else 'default'."""
    try:
        code, sink_name, _ = run_command(["pactl", "get-default-sink"])
        sink_name = sink_name.strip()
        if code == 0 and sink_name:
            candidate = f"{sink_name}.monitor"
            sources = [s for s, _ in list_pulse_sources()]
            if candidate in sources:
                return candidate
        # fallback: first *.monitor source
        for s, _ in list_pulse_sources():
            if s.endswith(".monitor"):
                logger.debug("Default sink has no monitor source, falling back to '%s'", s)
                return s
    except (FileNotFoundError, RuntimeError) as e:
        logger.debug("Could not query PulseAudio for a monitor source: %s", e)
    logger.debug("No monitor source found, falling back to 'default'")
    return "default"
