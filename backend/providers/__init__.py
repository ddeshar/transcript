from __future__ import annotations

from pathlib import Path

from .asr_base import ASRProvider
from .asr_cloud import WhisperCloudASRProvider
from .asr_mock import MockASRProvider
from .mt_base import MTProvider
from .mt_gtranslate import GoogleTranslateProvider
from .mt_awstranslate import AWSTranslateProvider
from .mt_openai_gpt import OpenAIGPTProvider
from .mt_mock import MockMTProvider
from .mt_simple_thai import SimpleThaiProvider

# TTS Providers
from .tts_base import TTSProvider, TTSVoice, TTSRequest, TTSResult
from .tts_openai import OpenAITTSProvider
from .tts_aws_polly import AWSPollyTTSProvider
from .tts_mock import MockTTSProvider

# Optional heavy dependencies - only import if available
try:
    from .asr_vosk import VoskASRProvider
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False
    VoskASRProvider = None

try:
    from .asr_whispercpp import WhisperCppASRProvider
    WHISPERCPP_AVAILABLE = True
except ImportError:
    WHISPERCPP_AVAILABLE = False
    WhisperCppASRProvider = None

try:
    from .asr_faster_whisper import FasterWhisperASRProvider
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    FasterWhisperASRProvider = None

try:
    from .asr_whisper_local import WhisperLocalProvider
    WHISPER_LOCAL_AVAILABLE = True
except ImportError:
    WHISPER_LOCAL_AVAILABLE = False
    WhisperLocalProvider = None

try:
    from .asr_hybrid import HybridASRProvider
    HYBRID_AVAILABLE = True
except ImportError:
    HYBRID_AVAILABLE = False
    HybridASRProvider = None

try:
    from .asr_openai_realtime import GPTRealtimeProvider, GPT4oAudioProvider
    OPENAI_REALTIME_AVAILABLE = True
except ImportError:
    OPENAI_REALTIME_AVAILABLE = False
    GPTRealtimeProvider = None
    GPT4oAudioProvider = None

try:
    from .mt_marian import MarianMTProvider
    MARIAN_AVAILABLE = True
except ImportError:
    MARIAN_AVAILABLE = False
    MarianMTProvider = None

try:
    from .mt_ctranslate2 import CTranslate2MTProvider
    CTRANSLATE2_AVAILABLE = True
except ImportError:
    CTRANSLATE2_AVAILABLE = False
    CTranslate2MTProvider = None


def create_asr_provider(
    name: str, *, base_dir: Path, settings: dict[str, str]
) -> ASRProvider:
    name = name.lower()
    if name == "mock":
        return MockASRProvider()
    # Handle removed providers with helpful error messages
    if name in ["vosk", "whispercpp", "faster_whisper"]:
        raise ValueError(f"Provider '{name}' removed: unreliable offline")
    if name == "whisper_gpt":
        raise ValueError("Provider 'whisper_gpt' removed: broken streaming")
    if name in ["whisper_local", "hybrid"]:
        raise ValueError(f"Provider '{name}' removed: depends on offline")
    
    if name == "whisper_api":
        return WhisperCloudASRProvider(
            api_key=settings.get("OPENAI_API_KEY"),
            model=settings.get("OPENAI_WHISPER_MODEL", "whisper-1"),
        )
    if name == "gpt_realtime":
        return GPTRealtimeProvider(
            api_key=settings.get("OPENAI_API_KEY"),
        )
    if name == "gpt_4o_audio":
        return GPT4oAudioProvider(
            api_key=settings.get("OPENAI_API_KEY"),
        )
    raise ValueError(f"Unsupported ASR provider: {name}")


def create_mt_provider(
    name: str, *, base_dir: Path, settings: dict[str, str]
) -> MTProvider:
    name = name.lower()
    if name == "mock":
        return MockMTProvider()
    if name in {"marian", "opus"}:
        if not MARIAN_AVAILABLE:
            raise RuntimeError("Marian MT not available.")
        model_dir = Path(
            settings.get("MARIAN_MODEL_DIR", base_dir / "models" / "marian")
        )
        model_name = settings.get(
            "MARIAN_MODEL_NAME", "Helsinki-NLP/opus-mt-en-th"
        )
        return MarianMTProvider(model_dir=model_dir, model_name=model_name)
    if name == "ctranslate2":
        if not CTRANSLATE2_AVAILABLE:
            raise RuntimeError("CTranslate2 not available.")
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
    if name == "gtranslate":
        return GoogleTranslateProvider(project_id=settings.get("GCP_PROJECT"))
    if name == "awstranslate":
        return AWSTranslateProvider(
            region_name=settings.get("AWS_REGION"),
            aws_access_key_id=settings.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=settings.get("AWS_SECRET_ACCESS_KEY"),
        )
    if name == "openai_gpt":
        return OpenAIGPTProvider(
            api_key=settings.get("OPENAI_API_KEY"),
            model=settings.get("OPENAI_GPT_MODEL", "gpt-3.5-turbo")
        )
    if name == "simple_thai":
        return SimpleThaiProvider()
    raise ValueError(f"Unsupported MT provider: {name}")


def create_tts_provider(name: str, **settings) -> TTSProvider:
    """Create TTS provider instance."""
    if name == "mock":
        return MockTTSProvider()
    if name == "openai":
        return OpenAITTSProvider(
            api_key=settings.get("OPENAI_API_KEY"),
            model=settings.get("OPENAI_TTS_MODEL", "tts-1")
        )
    if name == "aws_polly":
        return AWSPollyTTSProvider(
            access_key=settings.get("AWS_ACCESS_KEY_ID"),
            secret_key=settings.get("AWS_SECRET_ACCESS_KEY"),
            region=settings.get("AWS_REGION", "us-east-1")
        )
    raise ValueError(f"Unsupported TTS provider: {name}")


__all__ = ["create_asr_provider", "create_mt_provider"]
