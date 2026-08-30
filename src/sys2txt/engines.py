"""Transcription engines and the registry that selects between them.

An engine turns an audio file into a :class:`~sys2txt.formats.Transcript`. Each one
answers for itself what it is called, whether it can run here, and how to transcribe;
selecting between them is walking a registry, not a chain of ``if``\\ s.

    from sys2txt.engines import TranscriptionConfig, get_engine

    engine = get_engine("auto")
    transcript = engine.transcribe("audio.wav", TranscriptionConfig(model="small"))

Adding an engine means writing one class and adding it to :data:`ENGINES`; the ``auto``
preference order, the ``--engine`` choices and the "nothing is installed" error all
follow from the registry.

Backends are imported inside the engine that needs them, so importing this module costs
nothing and an uninstalled backend is a ``False`` from :meth:`is_available`, not an
``ImportError`` at import time.
"""

import json
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, List, Optional, Protocol, Tuple, runtime_checkable

from .constants import WHISPER_CPP_MODEL_URL_TEMPLATE, WHISPER_CPP_TIMEOUT
from .formats import Cue, Transcript

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionConfig:
    """Configuration for transcription that stays constant across calls."""

    engine: str = "auto"
    model: str = "small"
    device: str = "auto"
    language: Optional[str] = None
    timestamps: bool = False
    model_path: Optional[str] = None
    whisper_cpp_path: Optional[str] = None
    download_model: bool = True


@runtime_checkable
class TranscriptionEngine(Protocol):
    """One way of turning audio into a transcript.

    Attributes:
        name: The engine's ``--engine`` name
    """

    name: str

    def is_available(self) -> bool:
        """Return whether this engine can run on this machine.

        Only ``auto`` selection consults this. Naming an engine explicitly runs it
        regardless, so the user gets the backend's own diagnostic rather than a
        generic "not available".
        """
        ...

    def transcribe(self, path: str, config: TranscriptionConfig) -> Transcript:
        """Transcribe an audio file into timed cues.

        Args:
            path: Path to the audio file
            config: Transcription configuration

        Returns:
            The transcript, with cue times in seconds from the start of the file
        """
        ...

    def unload(self) -> None:
        """Release any cached model, freeing the memory it holds."""
        ...


def _resolve_device(device: str) -> str:
    """Resolve a ``--device`` choice to a device the Python backends understand.

    ``auto`` defers to ``SYS2TXT_DEVICE`` and then to CPU. The GPU choices that only
    whisper.cpp can honour (``vulkan``, ``gpu``) fall back to CPU here.

    Args:
        device: Device as chosen on the command line

    Returns:
        Either ``"cuda"`` or ``"cpu"``
    """
    if device == "auto":
        device = os.environ.get("SYS2TXT_DEVICE", "cpu")
    return "cuda" if device == "cuda" else "cpu"


class _CachedModelEngine:
    """Base for engines that load a model into memory and reuse it.

    Loading a Whisper model costs seconds, which live mode would otherwise pay for every
    segment, so the loaded model is kept until a call asks for a different one. The cache
    holds a single model: a second one would double the memory a transcription needs, and
    a run only ever uses one.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: Optional[Tuple[Any, ...]] = None
        self._model: Any = None

    def _get_model(self, key: Tuple[Any, ...], load: Callable[[], Any]) -> Any:
        """Return the cached model for ``key``, loading it if it is not the cached one."""
        with self._lock:
            if self._key != key:
                self._model = load()
                self._key = key
            return self._model

    def unload(self) -> None:
        """Drop the cached model, releasing the memory it holds."""
        with self._lock:
            self._model = None
            self._key = None


class FasterWhisperEngine(_CachedModelEngine):
    """faster-whisper: the ctranslate2 reimplementation, and the preferred engine."""

    name = "faster"

    def is_available(self) -> bool:
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            return False
        return True

    def transcribe(self, path: str, config: TranscriptionConfig) -> Transcript:
        try:
            from faster_whisper import WhisperModel  # type: ignore
        except ImportError as e:
            raise RuntimeError("faster-whisper is not installed. pip install faster-whisper") from e

        device = _resolve_device(config.device)
        compute_type = "float16" if device == "cuda" else "int8"

        def load() -> Any:
            logger.info("Loading faster-whisper model '%s' on %s (%s)", config.model, device, compute_type)
            return WhisperModel(config.model, device=device, compute_type=compute_type)

        model = self._get_model((config.model, device, compute_type), load)
        segments, info = model.transcribe(path, vad_filter=True, language=config.language)
        cues = tuple(Cue(start=float(seg.start), end=float(seg.end), text=seg.text.strip()) for seg in segments)
        return Transcript(cues=cues, language=getattr(info, "language", None) or config.language)


class OpenAIWhisperEngine(_CachedModelEngine):
    """openai-whisper: the reference implementation, used when faster-whisper is absent."""

    name = "whisper"

    def is_available(self) -> bool:
        try:
            import whisper  # noqa: F401
        except ImportError:
            return False
        return True

    def transcribe(self, path: str, config: TranscriptionConfig) -> Transcript:
        try:
            import whisper  # type: ignore
        except ImportError as e:
            raise RuntimeError("openai-whisper is not installed. pip install openai-whisper") from e

        device = _resolve_device(config.device)

        def load() -> Any:
            logger.info("Loading openai-whisper model '%s' on %s", config.model, device)
            return whisper.load_model(config.model, device=device)

        model = self._get_model((config.model, device), load)
        result = model.transcribe(path, language=config.language)
        detected = result.get("language") or config.language
        segments = result.get("segments") or []
        if segments:
            cues = tuple(
                Cue(
                    start=float(seg.get("start", 0.0)),
                    end=float(seg.get("end", 0.0)),
                    text=seg.get("text", "").strip(),
                )
                for seg in segments
            )
        else:
            # Untimed fallback: the whole transcript as a single cue of unknown extent.
            text = result.get("text", "").strip()
            cues = (Cue(start=0.0, end=0.0, text=text),) if text else ()
        return Transcript(cues=cues, language=detected)


def _resolve_whisper_cpp_binary(whisper_cpp_path: Optional[str]) -> str:
    """Resolve the path to the whisper-cli binary.

    Priority:
    1. Explicit path argument
    2. SYS2TXT_WHISPER_CPP environment variable
    3. PATH lookup for 'whisper-cli'

    Args:
        whisper_cpp_path: Explicit path to whisper-cli binary

    Returns:
        Path to whisper-cli binary

    Raises:
        RuntimeError: If binary cannot be found
    """
    if whisper_cpp_path:
        if not os.path.isfile(whisper_cpp_path):
            raise RuntimeError(f"whisper-cli binary not found at: {whisper_cpp_path}")
        return whisper_cpp_path

    env_path = os.environ.get("SYS2TXT_WHISPER_CPP")
    if env_path:
        if not os.path.isfile(env_path):
            raise RuntimeError(f"whisper-cli binary not found at SYS2TXT_WHISPER_CPP: {env_path}")
        return env_path

    path_lookup = shutil.which("whisper-cli")
    if path_lookup:
        return path_lookup

    raise RuntimeError(
        "whisper-cli binary not found. Install whisper.cpp and either:\n"
        "  1. Add whisper-cli to PATH\n"
        "  2. Set SYS2TXT_WHISPER_CPP environment variable\n"
        "  3. Use --whisper-cpp-path argument"
    )


def _download_whisper_cpp_model(model_filename: str, destination: Path) -> None:
    """Download a whisper.cpp GGML model from the ggerganov/whisper.cpp Hugging Face repo.

    Streams to a ``.part`` file alongside ``destination`` and renames it into place on
    success, so a failed or interrupted download never leaves a file that later looks
    like a complete model.

    Raises:
        RuntimeError: If the download fails for any reason
    """
    url = WHISPER_CPP_MODEL_URL_TEMPLATE.format(filename=model_filename)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")

    logger.info("Downloading whisper.cpp model '%s' from %s", model_filename, url)
    try:
        with urllib.request.urlopen(url) as response, open(partial, "wb") as f:
            total = response.getheader("Content-Length")
            total_bytes = int(total) if total else None
            written = 0
            last_logged_percent = -1
            while chunk := response.read(1024 * 1024):
                f.write(chunk)
                written += len(chunk)
                if total_bytes:
                    percent = written * 100 // total_bytes
                    if percent >= last_logged_percent + 10:
                        logger.info("Downloading %s: %d%%", model_filename, percent)
                        last_logged_percent = percent
    except (urllib.error.URLError, OSError) as e:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Failed to download whisper.cpp model '{model_filename}' from {url}: {e}") from e

    partial.rename(destination)
    logger.info("Downloaded whisper.cpp model to %s", destination)


def _resolve_whisper_cpp_model_path(model_path: Optional[str], model_size: str, download: bool = True) -> str:
    """Resolve the path to a whisper.cpp model file, downloading it if missing.

    Priority:
    1. Explicit model_path argument
    2. SYS2TXT_WHISPER_CPP_MODELS directory + ggml-{model_size}.bin
    3. ~/.local/share/whisper.cpp/models/ggml-{model_size}.bin

    If none of these exist and ``download`` is true, the model is fetched from the
    ggerganov/whisper.cpp Hugging Face repo into the resolved models directory
    (``SYS2TXT_WHISPER_CPP_MODELS`` if set, else the default directory above).

    Args:
        model_path: Explicit path to model file
        model_size: Whisper model size (tiny, base, small, medium, large-v2)
        download: Whether to attempt downloading a missing model

    Returns:
        Path to model file

    Raises:
        RuntimeError: If model file cannot be found or downloaded
    """
    if model_path:
        if not os.path.isfile(model_path):
            raise RuntimeError(f"whisper.cpp model not found at: {model_path}")
        return model_path

    model_filename = f"ggml-{model_size}.bin"

    env_models_dir = os.environ.get("SYS2TXT_WHISPER_CPP_MODELS")
    if env_models_dir:
        env_model_path = os.path.join(env_models_dir, model_filename)
        if os.path.isfile(env_model_path):
            return env_model_path

    default_dir = Path.home() / ".local" / "share" / "whisper.cpp" / "models"
    default_path = default_dir / model_filename
    if default_path.is_file():
        return str(default_path)

    target_dir = Path(env_models_dir) if env_models_dir else default_dir
    target_path = target_dir / model_filename

    if download:
        try:
            _download_whisper_cpp_model(model_filename, target_path)
        except RuntimeError as e:
            logger.warning("%s", e)
        else:
            return str(target_path)

    raise RuntimeError(
        f"whisper.cpp model '{model_filename}' not found. Either:\n"
        "  1. Use --model-path to specify the model file\n"
        f"  2. Set SYS2TXT_WHISPER_CPP_MODELS to directory containing {model_filename}\n"
        f"  3. Place model at {default_path}"
    )


def _parse_whisper_cpp_json(raw: str, language: Optional[str] = None) -> Transcript:
    """Parse whisper-cli's ``-oj`` JSON output.

    Each entry under ``transcription`` carries ``offsets.from``/``offsets.to`` in
    milliseconds alongside the display-only ``timestamps.from``/``timestamps.to``
    strings; the offsets are used since they need no format parsing of their own.
    ``result.language`` is whisper.cpp's own detected/used language and is preferred
    over the caller's requested language, which may have been ``None`` (auto-detect).

    Raises:
        RuntimeError: If ``raw`` is not the JSON object whisper-cli is documented to emit
    """
    try:
        data = json.loads(raw)
        segments = data["transcription"]
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise RuntimeError(f"whisper-cli produced unparseable JSON output: {e}") from e

    cues: List[Cue] = []
    for segment in segments:
        text = segment["text"].strip()
        if not text:
            continue
        offsets = segment["offsets"]
        cues.append(
            Cue(
                start=offsets["from"] / 1000.0,
                end=offsets["to"] / 1000.0,
                text=text,
            )
        )

    detected_language = data.get("result", {}).get("language")
    return Transcript(cues=tuple(cues), language=detected_language or language)


class WhisperCppEngine:
    """whisper.cpp: an external whisper-cli binary, with optional Vulkan GPU support.

    Nothing is cached: each transcription is a subprocess that loads the model itself.
    """

    name = "cpp"

    def is_available(self) -> bool:
        """Return whether a whisper-cli binary can be found on PATH or in the environment.

        An explicit ``--whisper-cpp-path`` is not visible here, but a user who passes it
        also names ``--engine cpp``, which skips this probe.
        """
        try:
            _resolve_whisper_cpp_binary(None)
        except RuntimeError:
            return False
        return True

    def unload(self) -> None:
        """No cached model to release."""

    def transcribe(self, path: str, config: TranscriptionConfig) -> Transcript:
        """Transcribe by running whisper-cli and parsing its ``-oj`` JSON output.

        The JSON is a structured interface (segment start/end/text as typed fields)
        rather than a display format, so it survives changes to whisper-cli's
        human-readable console output that broke #42.

        Raises:
            RuntimeError: If whisper-cli or its model cannot be found, or it fails
        """
        binary = _resolve_whisper_cpp_binary(config.whisper_cpp_path)
        model = _resolve_whisper_cpp_model_path(config.model_path, config.model, download=config.download_model)

        with tempfile.TemporaryDirectory(prefix="sys2txt-whisper-cpp-") as tmpdir:
            output_prefix = os.path.join(tmpdir, "output")
            json_path = output_prefix + ".json"

            cmd = [binary, "-m", model, "-f", path, "-np", "-oj", "-of", output_prefix]

            # Device selection
            if config.device == "cpu":
                cmd.append("--no-gpu")
            # For auto/vulkan/gpu/cuda, let whisper.cpp use GPU if available

            if config.language:
                cmd.extend(["-l", config.language])

            logger.debug("Running whisper-cli: %s", " ".join(cmd))
            try:
                subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=WHISPER_CPP_TIMEOUT)
            except subprocess.TimeoutExpired as e:
                raise RuntimeError(
                    f"whisper-cli timed out after {WHISPER_CPP_TIMEOUT} seconds "
                    f"(possible GPU hang or malformed audio): {binary}"
                ) from e
            except subprocess.CalledProcessError as e:
                stderr = e.stderr.strip() if e.stderr else "No error output"
                raise RuntimeError(f"whisper-cli failed: {stderr}") from e
            except FileNotFoundError as e:
                raise RuntimeError(f"whisper-cli binary not found: {binary}") from e

            try:
                raw = Path(json_path).read_text()
            except OSError as e:
                raise RuntimeError(f"whisper-cli did not produce the expected JSON output at {json_path}") from e

        return _parse_whisper_cpp_json(raw, config.language)


ENGINES: Tuple[TranscriptionEngine, ...] = (
    FasterWhisperEngine(),
    OpenAIWhisperEngine(),
    WhisperCppEngine(),
)
"The available engines, in the order ``auto`` prefers them"

ENGINE_NAMES: Tuple[str, ...] = ("auto",) + tuple(engine.name for engine in ENGINES)
"Valid ``--engine`` values: ``auto`` plus every registered engine"

_INSTALL_HINTS = {
    "faster": "pip install faster-whisper",
    "whisper": "pip install openai-whisper",
    "cpp": "build whisper.cpp and put whisper-cli on PATH",
}


def get_engine(name: str) -> TranscriptionEngine:
    """Return the engine to transcribe with.

    Args:
        name: An engine name, or ``"auto"`` to pick the first available one

    Returns:
        The selected engine

    Raises:
        ValueError: If ``name`` is not a known engine
        RuntimeError: If ``name`` is ``"auto"`` and no engine is installed
    """
    if name == "auto":
        for engine in ENGINES:
            if engine.is_available():
                logger.debug("Auto-selected transcription engine: %s", engine.name)
                return engine
        installs = "\n".join(f"  {engine.name}: {_INSTALL_HINTS[engine.name]}" for engine in ENGINES)
        raise RuntimeError(f"No transcription engine is installed. Install one of:\n{installs}")

    for engine in ENGINES:
        if engine.name == name:
            return engine

    raise ValueError(f"Unknown engine: {name}")


def unload_engines() -> None:
    """Release every engine's cached model."""
    for engine in ENGINES:
        engine.unload()
