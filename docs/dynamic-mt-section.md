# Dynamic MT Section - Feature Summary

## 🎯 What Was Implemented

The settings page now dynamically shows/hides the Machine Translation (MT) section based on whether the selected ASR provider needs it or not.

## 🔄 Dynamic Behavior

### When `requires_mt: true` (Standard ASR providers)
- **Vosk, Faster-Whisper, Whisper Local, WhisperCpp, Whisper API**
- MT section is **VISIBLE** and **ENABLED**
- Section title: "🌐 Translation (MT) **REQUIRED**"
- User must select an MT provider
- Section appears normal (full opacity)

### When `requires_mt: false` (Built-in Translation providers)  
- **GPT-4o Real-time, GPT-4o Audio, Whisper+GPT, Hybrid**
- MT section is **DIMMED** and **DISABLED**
- Section title: "🌐 Translation (MT) **NOT NEEDED - Built-in Translation**"
- Description shows: *"This ASR provider includes built-in translation capabilities. No separate MT provider is required."*
- Section appears faded (60% opacity, no pointer events)

## 🎨 Visual Indicators

**Required MT:**
```
🌐 Translation (MT) REQUIRED
[Full opacity, orange "REQUIRED" badge]
```

**Built-in Translation:**
```  
🌐 Translation (MT) NOT NEEDED - Built-in Translation
[Faded appearance, explanatory text]
```

## ⚡ Real-time Updates

- **Instant feedback**: When you change ASR provider in dropdown, MT section updates immediately
- **Smart saving**: Save function automatically uses recommended MT for built-in providers
- **Smooth transitions**: CSS animations for opacity and color changes

## 🧪 Testing the Feature

1. **Go to Settings**: http://localhost:8000/static/settings.html
2. **Try different ASR providers**:
   - Select `vosk` → MT section shows "REQUIRED" 
   - Select `gpt_realtime` → MT section shows "NOT NEEDED"
   - Select `whisper_api` → MT section shows "REQUIRED"
   - Select `gpt_4o_audio` → MT section shows "NOT NEEDED"

## 💰 Cost Benefits

This helps users understand:
- **Free combinations**: Local ASR + Local MT = $0
- **Premium real-time**: GPT Real-time = $18/hour (no MT needed)
- **Cost-effective**: Whisper API + Simple Thai = $0.36/hour
- **Best quality**: Whisper API + GPT MT = ~$3.36/hour

The dynamic UI makes it clear which providers need additional translation services and which come with built-in translation capabilities!