"""Mock MT provider for testing without models."""
from __future__ import annotations

from .mt_base import MTProvider, MTResult


class MockMTProvider(MTProvider):
    name = "mock"

    async def setup(self) -> None:
        pass

    async def translate(self, text: str, *, is_final: bool = False) -> MTResult:
        # Mock translation - just add Thai prefix
        thai_text = f"🇹🇭 {text} (mock)"
        return MTResult(
            text=thai_text,
            provider=self.name,
            is_final=is_final
        )