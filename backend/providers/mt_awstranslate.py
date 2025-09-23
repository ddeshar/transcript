from __future__ import annotations

import asyncio
from typing import Optional

import boto3

from .mt_base import MTProvider, MTResult
from ..utils import to_thread


class AWSTranslateProvider(MTProvider):
    name = "awstranslate"

    def __init__(self, region_name: Optional[str] = None) -> None:
        self.region_name = region_name
        self._client = None
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        async with self._lock:
            if self._client is None:
                self._client = boto3.client("translate", region_name=self.region_name)

    async def translate(self, text: str, *, is_final: bool) -> MTResult:
        if not text.strip():
            return MTResult(text="", provider=self.name, is_final=is_final)
        if self._client is None:
            raise RuntimeError("AWSTranslateProvider.setup() must be awaited before use.")
        response = await to_thread(
            self._client.translate_text,
            Text=text,
            SourceLanguageCode="en",
            TargetLanguageCode="th",
        )
        thai = response.get("TranslatedText", "").strip()
        return MTResult(text=thai, provider=self.name, is_final=is_final, raw=response)


__all__ = ["AWSTranslateProvider"]
