import asyncio
import json
import logging
import os
import time
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

_LOGGER: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    """Return a module-level structured logger configured once."""
    global _LOGGER
    if _LOGGER is None:
        logging.basicConfig(level=logging.INFO)
        _LOGGER = logging.getLogger("subtitle-app")
    return _LOGGER


def utc_timestamp_ms() -> int:
    """Return the current UTC timestamp in milliseconds."""
    return int(time.time() * 1000)


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    value = os.getenv(name)
    if value is None:
        return default
    return value


def get_bool_env(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off"}:
        return False
    return default


def session_id() -> str:
    return uuid.uuid4().hex


def pcm16_byte_length(samples: int) -> int:
    return samples * 2


def chunk_generator(data: bytes, size: int):
    for idx in range(0, len(data), size):
        yield data[idx: idx + size]


def jsonify_log(event: str, **fields: Any) -> None:
    logger = get_logger()
    payload: Dict[str, Any] = {"event": event, **fields}
    logger.info(json_dumps(payload))


async def to_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


class SessionTranscript:
    """Utility to track finalized subtitles for download."""

    def __init__(self) -> None:
        self._segments: list[Dict[str, Any]] = []

    def clear(self) -> None:
        self._segments.clear()

    def add_segment(self, segment: Dict[str, Any]) -> None:
        self._segments.append(segment)

    def to_serializable(self) -> Dict[str, Any]:
        return {
            "segments": self._segments,
            "generated_at": utc_timestamp_ms(),
        }

    def to_text(self) -> str:
        lines = []
        for item in self._segments:
            ts = item.get("timestamp_ms", 0)
            thai = item.get("thai", "")
            english = item.get("english", "")
            lines.append(f"[{format_timestamp(ts)}] {thai} (EN: {english})")
        return "\n".join(lines)


def format_timestamp(timestamp_ms: int) -> str:
    seconds, ms = divmod(timestamp_ms, 1000)
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"
