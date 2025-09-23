from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Optional


@dataclass
class MTResult:
    text: str
    provider: str
    is_final: bool
    raw: Optional[dict] = None


class MTProvider(abc.ABC):
    name: str

    @abc.abstractmethod
    async def setup(self) -> None:
        ...

    @abc.abstractmethod
    async def translate(self, text: str, *, is_final: bool) -> MTResult:
        ...


__all__ = ["MTResult", "MTProvider"]
