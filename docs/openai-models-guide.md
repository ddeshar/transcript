# OpenAI Models Guide - EN-TH Subtitle Application

## Real-time Models Added

### New ASR (Automatic Speech Recognition) Models

#### 1. GPT-4o Real-time Audio (`gpt_realtime`)
- **Purpose**: Real-time conversational AI with instant audio processing
- **Pricing**: $0.06/minute input, $0.24/minute output
- **Best for**: Live conversations, instant responses, real-time applications
- **Latency**: Ultra-low (< 100ms)
- **Quality**: Excellent for conversational context
- **Use case**: Perfect for live subtitling events or real-time conversations

#### 2. GPT-4o Audio Preview (`gpt_4o_audio`)
- **Purpose**: Audio input/output processing with GPT-4o capabilities  
- **Pricing**: $0.15 per 1M input tokens, $0.60 per 1M output tokens
- **Best for**: High-quality audio processing with context understanding
- **Latency**: Medium (1-3 seconds)
- **Quality**: Excellent understanding and context retention
- **Use case**: High-quality subtitle generation with contextual understanding

#### 3. Existing OpenAI Whisper API (`whisper_api`)
- **Purpose**: Speech-to-text transcription
- **Pricing**: $0.006/minute ($0.36/hour)
- **Best for**: Accurate English transcription
- **Latency**: Low (500ms - 2s)
- **Quality**: Excellent accuracy
- **Use case**: Cost-effective accurate transcription

## Recommendations by Use Case

### 🏆 Best Overall: Hybrid Approach
**Recommendation**: Use `hybrid` provider for optimal user experience
- Fast English transcription immediately (local models)  
- High-quality Thai translation later (cloud models)
- Best balance of speed, cost, and quality

### 💰 Most Cost-Effective: Local Models
**Recommendation**: `faster_whisper` + `marian`
- **ASR**: `faster_whisper` (Free, ~300ms latency)
- **Translation**: `marian` (Free, offline)
- **Total cost**: $0.00 (after initial setup)
- **Best for**: Budget-conscious deployments

### ⚡ Lowest Latency: GPT-4o Real-time
**Recommendation**: `gpt_realtime` 
- **Latency**: < 100ms end-to-end
- **Cost**: ~$0.30/minute ($18/hour)
- **Best for**: Live events where instant response is critical

### 🎯 Best Quality: GPT-4o Audio + OpenAI GPT
**Recommendation**: `gpt_4o_audio` + `openai_gpt`
- **Quality**: Superior contextual understanding
- **Cost**: Variable based on token usage
- **Best for**: Professional applications requiring highest quality

### 📈 Scalable Production: Whisper API + AWS/Google
**Recommendation**: `whisper_api` + `awstranslate`
- **ASR**: $0.006/minute
- **Translation**: $15/1M characters  
- **Best for**: Production applications with predictable costs

## Cost Comparison (per hour of audio)

| Model Combination | ASR Cost | Translation Cost | Total/Hour | Quality | Latency |
|-------------------|----------|------------------|------------|---------|---------|
| Local (Free) | $0.00 | $0.00 | **$0.00** | Good | Fast |
| Whisper + GPT | $0.36 | ~$3.00 | $3.36 | Excellent | Medium |
| GPT Real-time | $18.00 | Included | **$18.00** | Excellent | Ultra-fast |
| GPT Audio + GPT | ~$5.00 | ~$3.00 | $8.00 | Superior | Medium |

## Setup Instructions

1. **Add OpenAI API Key**: Set `OPENAI_API_KEY` in your environment
2. **Select Model**: Go to Settings → ASR Provider → Choose your model
3. **Configure Translation**: Choose appropriate MT provider based on your needs

## Model Availability

The new models (`gpt_realtime`, `gpt_4o_audio`) are available when:
- OpenAI API key is configured
- Application has been restarted after configuration
- Models appear in Settings → ASR Provider dropdown

## Performance Tips

1. **Real-time Applications**: Use `gpt_realtime` for live events
2. **Batch Processing**: Use `whisper_api` for recorded content  
3. **Development/Testing**: Use local models for cost-free development
4. **Production**: Consider `hybrid` for best user experience

## Pricing Updates

*Note: OpenAI pricing is subject to change. Check [OpenAI Pricing](https://openai.com/pricing) for latest rates.*

Last Updated: December 2024