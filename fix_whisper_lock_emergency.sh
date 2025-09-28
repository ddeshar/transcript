#!/bin/bash

echo "🚑 EMERGENCY FIX: Adding missing _lock attribute to WhisperAPIStream"
echo "Target: production server"

# Check if we're in the right directory
if [ ! -f "backend/providers/asr_cloud.py" ]; then
    echo "❌ Error: Not in transcript project directory"
    exit 1
fi

echo "📋 Current status:"
echo "   - Issue: AttributeError: 'WhisperAPIStream' object has no attribute '_lock'"
echo "   - Fix: Add self._lock = asyncio.Lock() to __init__ method"
echo "   - Impact: Critical - transcription completely broken"

echo ""
echo "🔧 Applying fix locally first..."

# Verify the fix is already applied
if grep -q "_lock = asyncio.Lock()" backend/providers/asr_cloud.py; then
    echo "✅ Fix already applied locally"
else
    echo "❌ Fix not found locally - please apply the _lock fix first"
    exit 1
fi

echo ""
echo "🚀 Ready to deploy emergency fix to production"
echo ""
echo "Run these commands on the production server:"
echo ""
echo "# 1. Backup current file"
echo "sudo cp /var/www/transcript/backend/providers/asr_cloud.py /var/www/transcript/backend/providers/asr_cloud.py.backup"
echo ""
echo "# 2. Update the file with the fix"
echo "# Add 'self._lock = asyncio.Lock()' after line 32 in the __init__ method"
echo ""
echo "# 3. Restart the service"
echo "cd /var/www/transcript/deploy && docker-compose restart transcript-app"
echo ""
echo "# 4. Verify fix"
echo "docker logs transcript-app -f | grep -E '(ERROR|AttributeError|_lock)'"
echo ""

echo "🎯 The exact line to add:"
echo "        self._lock = asyncio.Lock()"
echo ""
echo "📍 Add it after line 32, after:"
echo "        self._seq = 0"

echo ""
echo "💡 Alternative: Copy the fixed file directly:"
echo "scp backend/providers/asr_cloud.py ubuntu@your-server:/var/www/transcript/backend/providers/asr_cloud.py"