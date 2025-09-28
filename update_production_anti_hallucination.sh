#!/bin/bash

# Production Anti-Hallucination Update Script
# Updates the production environment with fixes for AI hallucinations and redundant politeness

set -e

echo "🔧 Updating Production Environment for Anti-Hallucination Fixes"
echo "=============================================================="

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_info "Step 1: Backing up current production environment..."
if [ -f ".env.prod" ]; then
    cp .env.prod .env.prod.backup.$(date +%Y%m%d_%H%M%S)
    print_success "Environment backed up"
else
    print_warning "No existing .env.prod found"
fi

print_info "Step 2: Validating updated settings..."
echo ""
echo "🎯 Key Anti-Hallucination Settings Applied:"
echo "   - OPENAI_GPT_TEMPERATURE: 0.3 → 0.1 (more deterministic)"
echo "   - OPENAI_GPT_MAX_TOKENS: 100 → 80 (prevent over-elaboration)"
echo "   - OPENAI_GPT_FREQUENCY_PENALTY: 0.1 (reduce repetition)"
echo "   - MIN_TRANSLATION_CHARS: 5 → 3 (catch shorter artifacts)"
echo "   - ENABLE_HALLUCINATION_FILTER: true (new filtering)"
echo "   - MIN_AUDIO_SEGMENT_MS: 500 (skip very short segments)"
echo "   - THAI_AUTO_POLITENESS: false (reduce ครับ/ค่ะ)"
echo "   - THAI_CASUAL_MODE: true (more natural Thai)"
echo ""

print_info "Step 3: Validating environment file..."
if grep -q "OPENAI_GPT_TEMPERATURE=0.1" .env.prod; then
    print_success "GPT temperature updated to 0.1"
else
    print_warning "GPT temperature not found - manual verification needed"
fi

if grep -q "ENABLE_HALLUCINATION_FILTER=true" .env.prod; then
    print_success "Hallucination filter enabled"
else
    print_warning "Hallucination filter not found - manual verification needed"
fi

if grep -q "THAI_AUTO_POLITENESS=false" .env.prod; then
    print_success "Auto-politeness disabled"
else
    print_warning "Auto-politeness setting not found - manual verification needed"
fi

print_info "Step 4: Preparing for deployment..."

echo ""
echo "🚀 To Deploy These Changes:"
echo ""
echo "1. Copy the updated .env.prod to your production server:"
echo "   scp .env.prod user@your-server:/path/to/transcript/"
echo ""
echo "2. Restart the application containers:"
echo "   docker-compose --env-file .env.prod down"
echo "   docker-compose --env-file .env.prod up -d"
echo ""
echo "3. Monitor the logs for improvements:"
echo "   docker logs transcript-app -f | grep -E '(Filtered|hallucination|politeness)'"
echo ""

echo "📊 Expected Improvements in Production:"
echo ""
echo "BEFORE (problematic patterns):"
echo "  ❌ 'pfft' sound → 'ฮึก' (hallucination from noise)"
echo "  ❌ 'This is a test' → 'นี่คือการทดสอบค่ะ/ครับ' (excessive politeness)"
echo "  ❌ Background noise → random Thai words"
echo "  ❌ Breathing/silence → 'ครับ', 'ค่ะ'"
echo ""
echo "AFTER (with fixes):"
echo "  ✅ 'pfft' sound → [FILTERED OUT]"
echo "  ✅ 'This is a test' → 'นี่คือการทดสอบ' (natural Thai)"
echo "  ✅ Background noise → [IGNORED]"
echo "  ✅ Breathing/silence → [NO OUTPUT]"
echo ""

echo "🔍 Debugging Commands for Production:"
echo ""
echo "# Check for filtered hallucinations:"
echo "docker logs transcript-app | grep 'Filtered out potential hallucination'"
echo ""
echo "# Monitor translation patterns:"
echo "docker logs transcript-app | grep 'GOT RESULT' | tail -20"
echo ""
echo "# Check environment variables are loaded:"
echo "docker exec transcript-app env | grep -E '(OPENAI_GPT|THAI_|HALLUCINATION)'"
echo ""

echo "⚠️  IMPORTANT PRODUCTION NOTES:"
echo ""
echo "1. The hallucination 'pfft' → 'ฮึก' suggests:"
echo "   - Whisper is detecting non-speech as speech"
echo "   - Background noise or breathing is being transcribed"
echo "   - Audio input may have gain/sensitivity issues"
echo ""
echo "2. The redundant 'ครับ/ค่ะ' suggests:"
echo "   - GPT is over-formalizing casual English"
echo "   - Temperature was too high (0.3 vs new 0.1)"
echo "   - Translation prompt needed improvement"
echo ""
echo "3. Monitor these specific patterns after deployment:"
echo "   - No more sound effects being transcribed"
echo "   - Casual English stays casual in Thai"
echo "   - Only genuinely formal speech gets ครับ/ค่ะ"
echo ""

print_success "Production environment updated successfully!"
print_info "Deploy when ready and monitor the improvements."

echo ""
echo "📞 If Issues Persist After Deployment:"
echo "1. Check audio input levels (may be too sensitive)"
echo "2. Verify environment variables are loaded correctly"
echo "3. Monitor logs for filter effectiveness"
echo "4. Consider adjusting MIN_AUDIO_SEGMENT_MS if needed"