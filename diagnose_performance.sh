#!/bin/bash
# Real-time Transcription Performance Analyzer
# This script helps diagnose latency and accuracy issues

echo "🔍 TRANSCRIPT PERFORMANCE DIAGNOSTICS"
echo "======================================"

# Detect environment file location
ENV_FILE=""
if [ -f "deploy/.env" ]; then
    ENV_FILE="deploy/.env"
    echo "📁 Using production config: deploy/.env"
elif [ -f ".env" ]; then
    ENV_FILE=".env"
    echo "📁 Using local config: .env"
else
    echo "❌ No .env file found in current directory or deploy/ folder"
    echo "Expected locations: ./deploy/.env or ./.env"
    exit 1
fi
echo ""

# Check current provider configuration
echo "📋 Current Configuration:"
echo "ASR Provider: $(grep ASR_PROVIDER "$ENV_FILE" | cut -d'=' -f2)"
echo "MT Provider: $(grep MT_PROVIDER "$ENV_FILE" | cut -d'=' -f2)"
echo "Min Silence: $(grep MIN_SILENCE_MS "$ENV_FILE" | cut -d'=' -f2)ms"
echo "Status Interval: $(grep STATUS_INTERVAL_MS "$ENV_FILE" | cut -d'=' -f2)ms"
echo ""

# Check OpenAI API key validity
echo "🔑 API Key Check:"
if grep -q "OPENAI_API_KEY=sk-" "$ENV_FILE"; then
    echo "✅ OpenAI API key format looks valid"
    # Test API connectivity (optional)
    if command -v curl >/dev/null 2>&1; then
        echo "🌐 Testing OpenAI API connectivity..."
        API_KEY=$(grep OPENAI_API_KEY "$ENV_FILE" | cut -d'=' -f2)
        if curl -s -H "Authorization: Bearer $API_KEY" https://api.openai.com/v1/models >/dev/null; then
            echo "✅ OpenAI API is accessible"
        else
            echo "❌ Cannot reach OpenAI API - check internet/firewall"
        fi
    fi
else
    echo "❌ OpenAI API key missing or invalid format"
fi
echo ""

# Performance expectations
echo "📊 Expected Performance with Current Settings:"
echo "ASR Latency: 200-800ms (OpenAI Whisper API)"
echo "Translation: 100-400ms (GPT-3.5-turbo)"
echo "Total E2E: 0.5-1.5 seconds"
echo ""

# Common issues and solutions
echo "🚨 Common Issues & Quick Fixes:"
echo ""
echo "HALLUCINATIONS (hearing words not spoken):"
echo "✓ Fixed: Set OPENAI_WHISPER_TEMPERATURE=0.0 (deterministic)"
echo "✓ Fixed: Set OPENAI_WHISPER_LANGUAGE=en (skip detection)"
echo "✓ Fixed: Reduced MIN_SILENCE_MS to 300ms"
echo "• Check microphone quality and background noise"
echo "• Ensure 16kHz mono audio input"
echo ""
echo "HIGH LATENCY (30-60 second delays):"
echo "✓ Fixed: Reduced STATUS_INTERVAL_MS to 200ms"
echo "✓ Fixed: Added streaming optimizations"
echo "✓ Fixed: Reduced silence detection threshold"
echo "• Check internet latency: ping api.openai.com"
echo "• Verify server CPU/RAM usage"
echo ""

# Test commands
echo "🧪 Test Commands (run these after restart):"
echo ""
echo "1. Test API latency:"
echo "   time curl -X POST https://api.openai.com/v1/audio/transcriptions \\"
echo "     -H 'Authorization: Bearer YOUR_API_KEY' \\"
echo "     -F 'file=@sample_audio/en_sample.wav' \\"
echo "     -F 'model=whisper-1'"
echo ""
echo "2. Monitor real-time logs:"
echo "   docker logs transcript-app -f | grep -E '(Processing|latency|ms)'"
echo ""
echo "3. Test WebSocket connection:"
echo "   Open browser console at https://your-domain.com"
echo "   Look for WebSocket connection logs"
echo ""

# Restart recommendation
echo "🔄 NEXT STEPS:"
if [ -f "deploy/docker-compose.prod.yml" ]; then
    echo "1. Restart the production app to apply new settings:"
    echo "   docker compose -f deploy/docker-compose.prod.yml restart app"
    echo ""
    echo "2. Check production logs:"
    echo "   docker compose -f deploy/docker-compose.prod.yml logs -f app"
elif [ -f "docker-compose.yml" ]; then
    echo "1. Restart the local app to apply new settings:"
    echo "   docker compose restart app"
    echo ""
    echo "2. Check local logs:"
    echo "   docker compose logs -f app"
else
    echo "1. Restart your app container (compose file not found in expected location)"
fi
echo ""
echo "3. Test with a short phrase (2-3 words first)"
echo "4. Check browser console for WebSocket errors"
echo "5. Monitor server logs for processing times"
echo ""
echo "Expected improvement: <2 second end-to-end latency"