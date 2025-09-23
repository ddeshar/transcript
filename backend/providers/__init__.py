from __future__ import annotations

from pathlib import Path
from typing import Optional

from .asr_base import ASRProvider
from .asr_vosk import VoskASRProvider
from .asr_whispercpp import WhisperCppASRProvider
from .asr_cloud import WhisperCloudASRProvider
from .asr_mock import MockASRProvider
from .mt_base import MTProvider
from .mt_marian import MarianMTProvider
from .mt_gtranslate import GoogleTranslateProvider
from .mt_awstranslate import AWSTranslateProvider
from .mt_mock import MockMTProvider


def create_asr_provider(name: str, *, base_dir: Path, settings: dict[str, str]) -> ASRProvider:
    name = name.lower()
    if name == "mock":
        return MockASRProvider()
    if name == "vosk":
        model_dir = Path(settings.get("VOSK_MODEL_DIR", base_dir / "models" / "vosk"))
        model_name = settings.get("VOSK_MODEL_NAME")
        return VoskASRProvider(model_dir=model_dir, model_name=model_name)
    if name == "whispercpp":
        model_path = Path(settings.get("WHISPER_CPP_MODEL_PATH", base_dir / "models" / "whisper.cpp" / "ggml-small.en.bin"))
        return WhisperCppASRProvider(model_path=model_path)
    if name in {"whisper_api", "openai"}:
        return WhisperCloudASRProvider(api_key=settings.get("OPENAI_API_KEY"), model=settings.get("OPENAI_WHISPER_MODEL", "whisper-1"))
    raise ValueError(f"Unsupported ASR provider: {name}")


def create_mt_provider(name: str, *, base_dir: Path, settings: dict[str, str]) -> MTProvider:
    name = name.lower()
    if name == "mock":
        return MockMTProvider()
    if name in {"marian", "opus"}:
        model_dir = Path(settings.get("MARIAN_MODEL_DIR", base_dir / "models" / "marian"))
        model_name = settings.get("MARIAN_MODEL_NAME", "Helsinki-NLP/opus-mt-en-th")
        return MarianMTProvider(model_dir=model_dir, model_name=model_name)
    if name in {"gtranslate", "google"}:
        return GoogleTranslateProvider(project_id=settings.get("GCP_PROJECT"))
    if name in {"awstranslate", "aws"}:
        return AWSTranslateProvider(region_name=settings.get("AWS_REGION"))
    raise ValueError(f"Unsupported MT provider: {name}")


__all__ = ["create_asr_provider", "create_mt_provider"]
