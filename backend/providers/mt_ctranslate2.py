from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional, Sequence, Any

from .mt_base import MTProvider, MTResult
from ..utils import ensure_dir, to_thread


class CTranslate2MTProvider(MTProvider):
    """Machine translation using a local CTranslate2 model.

    Expected model layout (default):
      models/ctranslate2/en-th/
        ├── config.json (optional)
        ├── model.bin / model.bin.* (required)
        ├── source.spm (or spm.model)
        └── target.spm (or spm.model)

    Notes:
    - Convert a HuggingFace model (e.g. Helsinki-NLP/opus-mt-en-th) with:
        ct2-transformers-converter \
          --model Helsinki-NLP/opus-mt-en-th \
          --output_dir models/ctranslate2/en-th \
          --copy_files source.spm target.spm vocab.spm
        - "source.spm" and "target.spm" are preferred; we fallback to
            "spm.model" if not found.
    """

    name = "ctranslate2"

    def __init__(
        self,
        *,
        model_dir: Path,
        src_spm: Optional[Path] = None,
        tgt_spm: Optional[Path] = None,
        device: str = "auto",
        compute_type: str = "auto",
        beam_size: int = 1,
        max_decoding_length: int = 256,
        source_prefix: str = "",
    ) -> None:
        self.model_dir = ensure_dir(model_dir)
        self.src_spm_path = (
            Path(src_spm) if src_spm else self.model_dir / "source.spm"
        )
        self.tgt_spm_path = (
            Path(tgt_spm) if tgt_spm else self.model_dir / "target.spm"
        )
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.max_len = max_decoding_length
        self.source_prefix = source_prefix.strip()

        # Lazy-loaded heavy deps; typed as Any to avoid import-time dependency
        self._translator: Optional[Any] = None
        self._src_sp: Optional[Any] = None
        self._tgt_sp: Optional[Any] = None
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        async with self._lock:
            if self._translator is not None:
                return

            def _load():
                import ctranslate2  # type: ignore  # lazy import
                import sentencepiece as spm  # type: ignore  # lazy import
                # Initialize translator
                translator = ctranslate2.Translator(
                    str(self.model_dir),
                    device=self.device,
                    compute_type=self.compute_type,
                )

                # Resolve SentencePiece model paths with fallbacks
                def _resolve_spm(path: Path) -> Path:
                    if path.exists():
                        return path
                    alt = self.model_dir / "spm.model"
                    if alt.exists():
                        return alt
                    raise FileNotFoundError(
                        "SentencePiece model not found at "
                        f"{path} or {alt}. "
                        "Make sure to copy/convert SPM files."
                    )

                src_path = _resolve_spm(self.src_spm_path)
                tgt_path = _resolve_spm(self.tgt_spm_path)

                src_sp = spm.SentencePieceProcessor()
                tgt_sp = spm.SentencePieceProcessor()
                # Some versions expose Load() instead of load(); call robustly
                if hasattr(src_sp, "load"):
                    src_sp.load(str(src_path))
                else:
                    src_sp.Load(str(src_path))
                if hasattr(tgt_sp, "load"):
                    tgt_sp.load(str(tgt_path))
                else:
                    tgt_sp.Load(str(tgt_path))

                return translator, src_sp, tgt_sp

            self._translator, self._src_sp, self._tgt_sp = await to_thread(
                _load
            )

    async def translate(self, text: str, *, is_final: bool) -> MTResult:
        if not text.strip():
            return MTResult(text="", provider=self.name, is_final=is_final)
        if (
            self._translator is None
            or self._src_sp is None
            or self._tgt_sp is None
        ):
            raise RuntimeError(
                "CTranslate2MTProvider.setup() must be awaited before use."
            )

        # Tokenize with SentencePiece
        def _prepare_tokens(t: str) -> Sequence[str]:
            if self.source_prefix:
                t = f"{self.source_prefix} {t}".strip()
            return self._src_sp.encode_as_pieces(t)

        src_tokens = await to_thread(_prepare_tokens, text)

        # Run translation
        results = await to_thread(
            self._translator.translate_batch,
            [src_tokens],
            beam_size=self.beam_size,
            max_decoding_length=self.max_len,
        )

        # Extract top hypothesis tokens and detokenize
        tgt_tokens: list[str] = _extract_tokens(results[0])
        thai: str = await to_thread(self._tgt_sp.decode_pieces, tgt_tokens)
        thai = thai.strip()
        return MTResult(
            text=thai,
            provider=self.name,
            is_final=is_final,
            raw={"tokens": tgt_tokens},
        )


def _extract_tokens(item: Any) -> list[str]:
    """Return the best hypothesis tokens from a CTranslate2 result item.

    The item shape varies across versions; we try common shapes.
    """
    # Object-like API
    for attr in ("hypotheses", "output", "tokens"):
        if hasattr(item, attr):
            val = getattr(item, attr)
            if isinstance(val, list) and val:
                # hypotheses/output could be list[list[str]]
                return val[0] if isinstance(val[0], list) else val
    # Dict-like API
    if isinstance(item, dict):
        for key in ("hypotheses", "output", "tokens"):
            if key in item and item[key]:
                val = item[key]
                return val[0] if isinstance(val[0], list) else val
    # Fallback
    return []


__all__ = ["CTranslate2MTProvider"]
