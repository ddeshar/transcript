from __future__ import annotations

import asyncio
from typing import Optional

from google.cloud import translate_v2 as translate

from .mt_base import MTProvider, MTResult
from ..utils import to_thread


class GoogleTranslateProvider(MTProvider):
    name = "gtranslate"

    def __init__(self, project_id: Optional[str] = None) -> None:
        self.project_id = project_id
        self._client: Optional[translate.Client] = None
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        async with self._lock:
            if self._client is None:
                self._client = translate.Client()

    async def translate(self, text: str, *, is_final: bool) -> MTResult:
        if not text.strip():
            return MTResult(text="", provider=self.name, is_final=is_final)
        if self._client is None:
            raise RuntimeError("GoogleTranslateProvider.setup() must be awaited before use.")
        response = await to_thread(
            self._client.translate,
            text,
            target_language="th",
            format_="text",
        )
        thai = response.get("translatedText", "").strip()
        return MTResult(text=thai, provider=self.name, is_final=is_final, raw=response)


__all__ = ["GoogleTranslateProvider"]
