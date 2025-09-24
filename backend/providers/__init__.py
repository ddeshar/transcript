from __future__ import annotations

from pathlib import Path

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
from .mt_ctranslate2 import CTranslate2MTProvider
from .mt_simple_thai import SimpleThaiProvider


def create_asr_provider(
    name: str, *, base_dir: Path, settings: dict[str, str]
) -> ASRProvider:
    name = name.lower()
    if name == "mock":
        return MockASRProvider()
    if name == "vosk":
        model_dir = Path(
            settings.get("VOSK_MODEL_DIR", base_dir / "models" / "vosk")
        )
        model_name = settings.get("VOSK_MODEL_NAME")
        return VoskASRProvider(model_dir=model_dir, model_name=model_name)
    if name == "whispercpp":
        model_path = Path(
            settings.get(
                "WHISPER_CPP_MODEL_PATH",
                base_dir / "models" / "whisper.cpp" / "ggml-small.en.bin",
            )
        )
        return WhisperCppASRProvider(model_path=model_path)
    if name in {"whisper_api", "openai"}:
        return WhisperCloudASRProvider(
            api_key=settings.get("OPENAI_API_KEY"),
            model=settings.get("OPENAI_WHISPER_MODEL", "whisper-1"),
        )
    raise ValueError(f"Unsupported ASR provider: {name}")


def create_mt_provider(
    name: str, *, base_dir: Path, settings: dict[str, str]
) -> MTProvider:
    name = name.lower()
    if name == "mock":
        return MockMTProvider()
    if name in {"marian", "opus"}:
        model_dir = Path(
            settings.get("MARIAN_MODEL_DIR", base_dir / "models" / "marian")
        )
        model_name = settings.get(
            "MARIAN_MODEL_NAME", "Helsinki-NLP/opus-mt-en-th"
        )
        return MarianMTProvider(model_dir=model_dir, model_name=model_name)
    if name in {"ctranslate2", "ct2"}:
        model_dir = Path(
            settings.get(
                "CT2_MODEL_DIR",
                base_dir / "models" / "ctranslate2" / "en-th",
            )
        )
        src_spm = settings.get("CT2_SOURCE_SPM")
        tgt_spm = settings.get("CT2_TARGET_SPM")
        device = settings.get("CT2_DEVICE", "auto")
        compute_type = settings.get("CT2_COMPUTE_TYPE", "auto")
        beam_size = int(settings.get("CT2_BEAM_SIZE", "1"))
        max_len = int(settings.get("CT2_MAX_LEN", "256"))
        source_prefix = settings.get("CT2_SOURCE_PREFIX", "")
        return CTranslate2MTProvider(
            model_dir=model_dir,
            src_spm=Path(src_spm) if src_spm else None,
            tgt_spm=Path(tgt_spm) if tgt_spm else None,
            device=device,
            compute_type=compute_type,
            beam_size=beam_size,
            max_decoding_length=max_len,
            source_prefix=source_prefix,
        )
    if name in {"gtranslate", "google"}:
        return GoogleTranslateProvider(project_id=settings.get("GCP_PROJECT"))
    if name in {"awstranslate", "aws"}:
        return AWSTranslateProvider(region_name=settings.get("AWS_REGION"))
    if name in {"simple_thai", "simple"}:
        return SimpleThaiProvider()
    raise ValueError(f"Unsupported MT provider: {name}")


__all__ = ["create_asr_provider", "create_mt_provider"]
