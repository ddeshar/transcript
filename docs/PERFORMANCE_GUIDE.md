# Performance Optimization Guide for Real-Time Transcription

## Current Issues & Solutions

### 1. AI Hallucinations (Root Cause: Mock Providers)
**Problem**: Your `.env` uses `ASR_PROVIDER=mock` and `MT_PROVIDER=mock`
**Solution**: Switch to real providers with your API keys

### 2. High Latency (30-60 seconds delay)
**Root Causes**:
- Mock providers don't process real audio
- Large buffer sizes (600ms silence detection)
- Slow update intervals (1000ms status updates)
- No streaming optimization

## Recommended Provider Combinations (Best to Worst)

### 🥇 **Option 1: OpenAI Stack (FASTEST)**
```env
ASR_PROVIDER=whisper_api          # OpenAI Whisper API
MT_PROVIDER=openai_gpt           # GPT-3.5/4 for translation
TTS_PROVIDER=openai              # OpenAI TTS
```
**Latency**: 200-800ms end-to-end
**Accuracy**: Excellent (95%+)
**Cost**: ~$0.006/minute for transcription + $0.002/request for translation

### 🥈 **Option 2: Hybrid Cloud (BALANCED)**
```env
ASR_PROVIDER=whisper_api          # OpenAI Whisper API
MT_PROVIDER=gtranslate           # Google Translate
TTS_PROVIDER=google              # Google TTS
```
**Latency**: 300-1000ms
**Accuracy**: Very Good (90-95%)
**Cost**: Lower translation costs

### 🥉 **Option 3: Local Faster-Whisper (OFFLINE)**
```env
ASR_PROVIDER=faster_whisper      # Local Whisper model
MT_PROVIDER=openai_gpt          # GPT for translation (still needs API)
TTS_PROVIDER=openai             # OpenAI TTS
```
**Latency**: 500-1500ms (depends on hardware)
**Accuracy**: Good (85-90%)
**Privacy**: Audio stays on server

### ❌ **Avoid These Combinations**
- `vosk` ASR: Slower and less accurate than Faster-Whisper
- `marian` MT: Much slower than cloud APIs
- Any `mock` provider: Returns fake data

## Critical Optimization Settings

### Audio Processing (Reduce Latency)
```env
MIN_SILENCE_MS=300               # Was 600ms - faster detection
STATUS_INTERVAL_MS=100          # Was 1000ms - more responsive
WHISPER_CHUNK_DURATION=1.0      # 1-second chunks
VAD_SENSITIVITY=0.6             # More sensitive voice detection
```

### Whisper Model Selection
```env
# For faster_whisper (local):
WHISPER_MODEL_SIZE=small        # Balance speed/accuracy
WHISPER_BEAM_SIZE=1            # Fastest inference
WHISPER_LANGUAGE=en            # Skip auto-detection
WHISPER_COMPUTE_TYPE=float16   # GPU optimization

# For OpenAI API:
OPENAI_WHISPER_MODEL=whisper-1  # Latest model
OPENAI_WHISPER_LANGUAGE=en     # Skip auto-detection
```

### Translation Optimization
```env
# OpenAI GPT (recommended):
OPENAI_MODEL=gpt-3.5-turbo     # Fastest model
OPENAI_MAX_TOKENS=150          # Limit length
OPENAI_TEMPERATURE=0.3         # Balance accuracy/naturalness

# Google Translate (alternative):
# Very fast, slightly less context-aware
```

## Hardware Requirements by Provider

### OpenAI API Stack
- **CPU**: Any modern CPU (processing is cloud-based)
- **RAM**: 2-4GB for app
- **Network**: Stable internet, <100ms latency to OpenAI
- **Cost**: ~$0.01/minute total

### Local Faster-Whisper
- **CPU**: 8+ cores recommended
- **RAM**: 8-16GB (model size dependent)
- **GPU**: RTX 3060+ or equivalent (optional but 3-5x faster)
- **Storage**: 2-8GB for models

## Implementation Steps

1. **Choose your provider combination** (recommend Option 1)

2. **Get API keys**:
   - OpenAI: https://platform.openai.com/api-keys
   - Google Cloud: Enable Translate/TTS APIs
   - AWS: Create IAM user with Polly/Translate access

3. **Update your production environment**:
   ```bash
   # Copy optimized config
   cp deploy/.env.optimized deploy/.env
   
   # Edit with your keys
   nano deploy/.env
   
   # Restart with new config
   docker compose -f deploy/docker-compose.prod.yml down
   docker compose -f deploy/docker-compose.prod.yml up -d --build
   ```

4. **Test latency**:
   ```bash
   # Monitor logs for timing info
   docker logs transcript-app -f | grep "Processing time"
   ```

## Expected Performance After Optimization

| Metric | Before (Mock) | After (OpenAI) | After (Local) |
|--------|---------------|----------------|---------------|
| Transcription | N/A (fake) | 200-500ms | 500-1500ms |
| Translation | N/A (fake) | 100-300ms | 100-300ms |
| End-to-End | 30-60s | 0.5-1.5s | 1-3s |
| Accuracy | 0% | 95%+ | 85-90% |

## Troubleshooting Common Issues

### Still Getting Delays?
1. Check internet latency: `ping api.openai.com`
2. Verify API keys are valid
3. Monitor CPU/RAM usage
4. Check audio chunk processing in logs

### Poor Accuracy?
1. Test microphone quality
2. Verify audio format (16kHz, mono, 16-bit)
3. Try different Whisper models
4. Check background noise levels

### API Errors?
1. Verify API quotas/billing
2. Check rate limits
3. Monitor error logs for specific issues