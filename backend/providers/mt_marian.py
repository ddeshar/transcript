from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from transformers import pipeline

from .mt_base import MTProvider, MTResult
from ..utils import ensure_dir, to_thread


class MarianMTProvider(MTProvider):
    name = "marian"

    def __init__(self, model_dir: Path, model_name: str = "Helsinki-NLP/opus-mt-en-th") -> None:
        self.model_dir = ensure_dir(model_dir)
        self.model_name = model_name
        self._pipeline = None
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        async with self._lock:
            if self._pipeline is not None:
                return
            self._pipeline = await to_thread(
                pipeline,
                "translation_en_to_th",
                model=str(self.model_dir) if self.model_dir.exists() else self.model_name,
                device=-1,
            )

    async def translate(self, text: str, *, is_final: bool) -> MTResult:
        if not text.strip():
            return MTResult(text="", provider=self.name, is_final=is_final)
        if self._pipeline is None:
            raise RuntimeError("MarianMTProvider.setup() must be awaited before use.")
        result = await to_thread(self._pipeline, text, max_length=512)
        thai = result[0]["translation_text"].strip()
        return MTResult(text=thai, provider=self.name, is_final=is_final, raw=result[0])


__all__ = ["MarianMTProvider"]
