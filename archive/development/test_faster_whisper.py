#!/usr/bin/env python3
"""
Standalone real-time transcription using faster-whisper.
This demonstrates the faster-whisper functionality similar to your provided code.
"""
import sys
import queue
import threading
import numpy as np
import argparse
from pathlib import Path

try:
    import sounddevice as sd
    from faster_whisper import WhisperModel
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("\nTo install dependencies:")
    print("pip install sounddevice faster-whisper")
    sys.exit(1)

# ---------------------------
# Config (tweak as you like)
# ---------------------------
SAMPLE_RATE = 16000          # Hz (Whisper native)
BLOCK_DURATION = 0.5         # seconds per audio callback
CHUNK_DURATION = 2.0         # seconds of audio per transcription
CHANNELS = 1                 # mono mic

MODEL_SIZE = "small"         # tiny/base/small/medium/large-v2/large-v3
DEVICE = "cpu"               # faster-whisper on Mac: use "cpu"
COMPUTE_TYPE = "int8"        # fastest on M1; try "int8_float16" for more accuracy

BEAM_SIZE = 1                # 1 = max speed (greedy). Increase for accuracy (slower).
LANGUAGE = "en"              # set None to auto-detect

# ---------------------------
# Derived values
# ---------------------------
FRAMES_PER_BLOCK = int(SAMPLE_RATE * BLOCK_DURATION)
FRAMES_PER_CHUNK = int(SAMPLE_RATE * CHUNK_DURATION)

audio_q: queue.Queue[np.ndarray] = queue.Queue()
audio_buffer = []


def init_model():
    print(f"Loading model: {MODEL_SIZE} (device={DEVICE}, compute_type={COMPUTE_TYPE})...")
    model = WhisperModel(MODEL_SIZE, device=DEVICE, compute_type=COMPUTE_TYPE)
    print("✅ Model loaded.")
    return model


def audio_callback(indata, frames, time, status):
    if status:
        # Non-fatal stream messages (under/overruns, etc.)
        print(f"[audio status] {status}", file=sys.stderr)
    # Copy to avoid referencing the internal buffer
    audio_q.put(indata.copy())


def recorder():
    """Continuously grabs mic audio and pushes blocks into a queue."""
    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            callback=audio_callback,
            blocksize=FRAMES_PER_BLOCK,
        ):
            print("🎤 Listening... Press Ctrl+C to stop.")
            while True:
                sd.sleep(100)
    except Exception as e:
        print("\n[recorder error]", e)
        print("\nTip: If you get a device error, list devices with:")
        print("  python -c \"import sounddevice as sd; print(sd.query_devices())\"")
        raise


def transcriber(model: WhisperModel):
    """Pulls audio blocks from the queue, batches them into CHUNK_DURATION windows, then transcribes."""
    global audio_buffer
    while True:
        block = audio_q.get()
        audio_buffer.append(block)

        total_frames = sum(len(b) for b in audio_buffer)
        if total_frames >= FRAMES_PER_CHUNK:
            # Concatenate and trim to exact chunk size
            audio_data = np.concatenate(audio_buffer)[:FRAMES_PER_CHUNK]
            audio_buffer = []  # reset buffer

            # Whisper expects mono float32 PCM array
            audio_data = audio_data.flatten().astype(np.float32)

            # Transcribe
            segments, _ = model.transcribe(
                audio_data,
                language=LANGUAGE,
                beam_size=BEAM_SIZE,
                vad_filter=False,            # set True if you want extra VAD (slightly slower)
            )

            # Print text from segments (no timestamps for max speed)
            text = "".join(seg.text for seg in segments).strip()
            if text:
                print(f"🗣️  {text}")


def main():
    parser = argparse.ArgumentParser(
        description="Real-time transcription with faster-whisper"
    )
    parser.add_argument(
        "--file", type=Path, help="Test with audio file instead of microphone"
    )
    parser.add_argument(
        "--model", default="small", help="Model size (default: small)"
    )
    parser.add_argument("--device", default="cpu", help="Device (default: cpu)")
    parser.add_argument(
        "--language", default="en", help="Language (default: en)"
    )

    args = parser.parse_args()

    # Use args directly instead of globals
    model_size = args.model
    device = args.device
    language = args.language

    print("🚀 Faster-Whisper Real-time Transcription")
    print(f"📊 Config: model={model_size}, device={device}, language={language}")
    print("-" * 60)

    # Initialize model with config
    print(f"Loading model: {model_size} (device={device}, compute_type={COMPUTE_TYPE})...")
    model = WhisperModel(model_size, device=device, compute_type=COMPUTE_TYPE)
    print("✅ Model loaded.")

    if args.file:
        # Test with file
        test_from_file(model, args.file, language)
    else:
        # Real-time transcription
        # Start recorder in a daemon thread so it stops with Ctrl+C
        threading.Thread(target=recorder, daemon=True).start()

        try:
            transcriber_with_config(model, language)
        except KeyboardInterrupt:
            print("\n🛑 Stopping… Bye!")
        except Exception as e:
            print(f"\n❌ [transcriber error] {e}")


def test_from_file(model: WhisperModel, audio_file: Path, language: str):
    """Test transcription from an audio file instead of microphone."""
    try:
        import soundfile as sf

        print(f"📁 Loading audio file: {audio_file}")
        audio_data, sr = sf.read(str(audio_file))

        # Resample if needed (simple approach)
        if sr != SAMPLE_RATE:
            print(f"⚠️  Audio sample rate {sr} != {SAMPLE_RATE}, results may vary")

        # Convert to mono if stereo
        if len(audio_data.shape) > 1:
            audio_data = audio_data.mean(axis=1)

        # Ensure float32
        audio_data = audio_data.astype(np.float32)

        print("🔄 Transcribing...")
        segments, _ = model.transcribe(
            audio_data,
            language=language,
            beam_size=BEAM_SIZE,
            vad_filter=False,
        )

        print("\n📝 Transcription Result:")
        print("=" * 50)
        for segment in segments:
            print(f"[{segment.start:.1f}s - {segment.end:.1f}s] {segment.text}")
        print("=" * 50)

    except ImportError:
        print("❌ soundfile not installed. Install with: pip install soundfile")
    except Exception as e:
        print(f"❌ Error processing file: {e}")


def transcriber_with_config(model: WhisperModel, language: str):
    """Transcriber function that uses passed language instead of global."""
    global audio_buffer
    while True:
        block = audio_q.get()
        audio_buffer.append(block)

        total_frames = sum(len(b) for b in audio_buffer)
        if total_frames >= FRAMES_PER_CHUNK:
            # Concatenate and trim to exact chunk size
            audio_data = np.concatenate(audio_buffer)[:FRAMES_PER_CHUNK]
            audio_buffer = []  # reset buffer

            # Whisper expects mono float32 PCM array
            audio_data = audio_data.flatten().astype(np.float32)

            # Transcribe
            segments, _ = model.transcribe(
                audio_data,
                language=language,
                beam_size=BEAM_SIZE,
                vad_filter=False,
            )

            # Print text from segments (no timestamps for max speed)
            text = "".join(seg.text for seg in segments).strip()
            if text:
                print(f"🗣️  {text}")


if __name__ == "__main__":
    main()