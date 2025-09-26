from __future__ import annotations

from pathlib import Path

from .asr_base import ASRProvider
from .asr_cloud import WhisperCloudASRProvider
from .asr_whisper_gpt import WhisperGPTProvider
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
    if name == "vosk":
        if not VOSK_AVAILABLE:
            raise RuntimeError("Vosk not available. Install with: pip install vosk")
        model_dir = Path(
            settings.get("VOSK_MODEL_DIR", base_dir / "models" / "vosk")
        )
        model_name = settings.get("VOSK_MODEL_NAME")
        return VoskASRProvider(model_dir=model_dir, model_name=model_name)
    if name == "whispercpp":
        if not WHISPERCPP_AVAILABLE:
            raise RuntimeError("WhisperCpp not available.")
        model_path = Path(
            settings.get(
                "WHISPER_CPP_MODEL_PATH",
                base_dir / "models" / "whisper.cpp" / "ggml-small.en.bin",
            )
        )
        return WhisperCppASRProvider(model_path=model_path)
    if name == "faster_whisper":
        if not FASTER_WHISPER_AVAILABLE:
            raise RuntimeError("Faster-whisper not available.")
        model_size = settings.get("FASTER_WHISPER_MODEL", "small")
        device = settings.get("FASTER_WHISPER_DEVICE", "cpu")
        compute_type = settings.get("FASTER_WHISPER_COMPUTE_TYPE", "int8")
        language = settings.get("FASTER_WHISPER_LANGUAGE", "en")
        beam_size = int(settings.get("FASTER_WHISPER_BEAM_SIZE", "1"))
        chunk_duration = float(
            settings.get("FASTER_WHISPER_CHUNK_DURATION", "2.0")
        )
        return FasterWhisperASRProvider(
            model_size=model_size,
            device=device,
            compute_type=compute_type,
            language=language,
            beam_size=beam_size,
            chunk_duration=chunk_duration,
        )
    if name == "whisper_api":
        return WhisperCloudASRProvider(
            api_key=settings.get("OPENAI_API_KEY"),
            model=settings.get("OPENAI_WHISPER_MODEL", "whisper-1"),
        )
    if name == "whisper_gpt":
        return WhisperGPTProvider(
            api_key=settings.get("OPENAI_API_KEY"),
            whisper_model=settings.get("OPENAI_WHISPER_MODEL", "whisper-1"),
            gpt_model=settings.get("OPENAI_GPT_MODEL", "gpt-3.5-turbo"),
        )
    if name == "whisper_local":
        model_size = settings.get("WHISPER_MODEL_SIZE", "base")
        device = settings.get("WHISPER_DEVICE", "cpu")
        chunk_duration = float(
            settings.get("WHISPER_CHUNK_DURATION", "2.0")
        )
        return WhisperLocalProvider(
            model_size=model_size,
            device=device,
            chunk_duration=chunk_duration,
        )
    if name == "gpt_realtime":
        return GPTRealtimeProvider(
            api_key=settings.get("OPENAI_API_KEY"),
        )
    if name == "gpt_4o_audio":
        return GPT4oAudioProvider(
            api_key=settings.get("OPENAI_API_KEY"),
        )
    if name == "hybrid":
        # Create fast provider (faster-whisper)
        fast_provider = FasterWhisperASRProvider(
            model_size=settings.get("FASTER_WHISPER_MODEL", "tiny"),
            device=settings.get("FASTER_WHISPER_DEVICE", "cpu"),
            compute_type=settings.get("FASTER_WHISPER_COMPUTE_TYPE", "int8"),
            language=settings.get("FASTER_WHISPER_LANGUAGE", "en"),
            beam_size=int(settings.get("FASTER_WHISPER_BEAM_SIZE", "1")),
            chunk_duration=float(
                settings.get("FASTER_WHISPER_CHUNK_DURATION", "1.0")
            ),
        )
        
        # Create quality provider (whisper API + GPT) if API key available
        quality_provider = None
        if settings.get("OPENAI_API_KEY"):
            quality_provider = WhisperGPTProvider(
                api_key=settings.get("OPENAI_API_KEY"),
                whisper_model=settings.get("OPENAI_WHISPER_MODEL", "whisper-1"),
                gpt_model=settings.get("OPENAI_GPT_MODEL", "gpt-3.5-turbo"),
            )
        
        return HybridASRProvider(
            fast_provider=fast_provider,
            quality_provider=quality_provider,
            enable_quality=quality_provider is not None,
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
