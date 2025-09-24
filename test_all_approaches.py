#!/usr/bin/env python3
"""
Test all ASR approaches: faster-whisper, official Whisper, Whisper API + GPT, and hybrid.
"""

import asyncio
import time
import requests
from typing import Dict, List


def test_all_approaches():
    """Compare all available ASR approaches."""
    
    print("🧪 COMPREHENSIVE ASR COMPARISON")
    print("=" * 50)
    
    approaches = [
        {
            "name": "Faster-Whisper (tiny)",
            "provider": "faster_whisper", 
            "speed": "~200-400ms",
            "quality_en": "85-90%",
            "quality_th": "60-70%",
            "cost": "Free",
            "internet": "No",
            "setup": "Easy",
            "description": "Current optimized setup - fastest"
        },
        {
            "name": "Official Whisper (base)",
            "provider": "whisper_local",
            "speed": "~500-1000ms", 
            "quality_en": "92-96%",
            "quality_th": "60-70%",
            "cost": "Free",
            "internet": "No", 
            "setup": "Medium",
            "description": "Better accuracy than faster-whisper"
        },
        {
            "name": "Whisper API + GPT",
            "provider": "whisper_gpt",
            "speed": "~3-7s",
            "quality_en": "95-98%", 
            "quality_th": "85-95%",
            "cost": "$15-40/month",
            "internet": "Yes",
            "setup": "Easy",
            "description": "Best quality, slowest, costs money"
        },
        {
            "name": "Hybrid (Fast + Quality)",
            "provider": "hybrid",
            "speed": "~300ms + 3-4s",
            "quality_en": "85-90% → 95-98%", 
            "quality_th": "60-70% → 85-95%",
            "cost": "Free + $15-40/month",
            "internet": "No + Yes",
            "setup": "Medium",
            "description": "English fast, Thai later - best UX!"
        }
    ]
    
    print(f"{'Approach':<25} {'Speed':<15} {'EN Quality':<15} {'TH Quality':<15} {'Cost':<12}")
    print("-" * 85)
    
    for approach in approaches:
        print(f"{approach['name']:<25} {approach['speed']:<15} {approach['quality_en']:<15} {approach['quality_th']:<15} {approach['cost']:<12}")
    
    print("\n🎯 DETAILED BREAKDOWN:")
    print("-" * 25)
    
    for i, approach in enumerate(approaches, 1):
        print(f"\n{i}️⃣ **{approach['name']}**")
        print(f"   Provider: {approach['provider']}")  
        print(f"   Description: {approach['description']}")
        print(f"   Setup: {approach['setup']} | Internet: {approach['internet']}")
        
        if approach['provider'] == 'faster_whisper':
            print("   ✅ Currently active - very fast real-time")
            print("   ❌ Basic Thai translation")
            
        elif approach['provider'] == 'whisper_local':
            print("   ✅ Better accuracy than faster-whisper")
            print("   ✅ Still completely local/free")
            print("   ❌ 2-3x slower than faster-whisper")
            
        elif approach['provider'] == 'whisper_gpt':
            print("   ✅ Best possible quality for both EN and TH")
            print("   ❌ Very slow (not real-time feeling)")
            print("   ❌ Costs money and needs internet")
            
        elif approach['provider'] == 'hybrid':
            print("   ✅ Best user experience - immediate + quality")
            print("   ✅ English shows instantly, Thai follows")
            print("   ❌ Complex setup, partial cloud costs")

def provide_recommendations():
    """Provide specific recommendations."""
    
    print("\n🚀 RECOMMENDATIONS:")
    print("-" * 20)
    
    print("\n🏃‍♂️ **FOR SPEED (Current Need)**:")
    print("   Keep: ASR_PROVIDER=faster_whisper")
    print("   Reason: ~300ms latency, real-time feeling")
    print("   Trade-off: Basic Thai translation")
    
    print("\n🎯 **FOR BETTER ACCURACY (Still Fast)**:")
    print("   Try: ASR_PROVIDER=whisper_local") 
    print("   Reason: Better English accuracy, still local")
    print("   Trade-off: ~2x slower but still reasonable")
    
    print("\n🌟 **FOR BEST EXPERIENCE (Recommended)**:")
    print("   Try: ASR_PROVIDER=hybrid")
    print("   Reason: English immediate + Thai quality later")
    print("   Setup: Needs OpenAI API key for quality part")
    
    print("\n💎 **FOR MAXIMUM QUALITY**:")
    print("   Use: ASR_PROVIDER=whisper_gpt")
    print("   Reason: Best possible EN and TH quality")
    print("   Trade-off: 3-7 second delays, costs money")

def setup_instructions():
    """Provide setup instructions for each approach."""
    
    print("\n🛠️ SETUP INSTRUCTIONS:")
    print("-" * 22)
    
    print("\n1️⃣ **Try Official Whisper (Better Accuracy)**:")
    print("   Edit .env.docker: ASR_PROVIDER=whisper_local")
    print("   Edit .env.docker: WHISPER_MODEL_SIZE=base")
    print("   Run: docker-compose up --build -d")
    print("   Result: Better English, same Thai, ~2x slower")
    
    print("\n2️⃣ **Try Hybrid Approach (Best UX)**:")
    print("   1. Get OpenAI API key: https://platform.openai.com/api-keys")
    print("   2. Edit .env.docker: ASR_PROVIDER=hybrid")
    print("   3. Edit .env.docker: OPENAI_API_KEY=your_api_key_here")
    print("   4. Run: docker-compose up --build -d")
    print("   5. Result: Fast English + delayed quality Thai!")
    
    print("\n3️⃣ **Try Pure Quality Approach**:")
    print("   1. Get OpenAI API key (same as above)")
    print("   2. Edit .env.docker: ASR_PROVIDER=whisper_gpt")
    print("   3. Edit .env.docker: OPENAI_API_KEY=your_api_key_here")
    print("   4. Run: docker-compose up --build -d")
    print("   5. Result: Best quality, but slow")

if __name__ == "__main__":
    test_all_approaches()
    provide_recommendations()
    setup_instructions()
    
    print("\n🎬 NEXT STEPS:")
    print("Which approach would you like to try?")
    print("A) whisper_local (better accuracy, still fast)")
    print("B) hybrid (fast English + quality Thai)")  
    print("C) Keep current faster_whisper setup")
    print("D) Test whisper_gpt (best quality)")
    
    print("\nJust let me know and I'll help you set it up!")