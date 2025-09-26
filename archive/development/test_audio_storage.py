#!/usr/bin/env python3
"""
Test script to simulate audio recording and verify local file creation
"""

import os
import sys
import wave
import struct
import math
from pathlib import Path

def create_test_audio_file(output_path: str, duration_seconds: float = 5.0, sample_rate: int = 16000):
    """Create a test WAV file with a sine wave tone"""
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Generate sine wave data
    frames = int(duration_seconds * sample_rate)
    frequency = 440.0  # A4 note
    
    audio_data = []
    for i in range(frames):
        # Generate sine wave sample
        sample = int(32767 * math.sin(2 * math.pi * frequency * i / sample_rate))
        audio_data.append(struct.pack('<h', sample))  # 16-bit little-endian
    
    # Write WAV file
    with wave.open(output_path, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b''.join(audio_data))
    
    print(f"✓ Created test audio file: {output_path}")
    print(f"  Duration: {duration_seconds}s")
    print(f"  Sample rate: {sample_rate}Hz")
    print(f"  File size: {os.path.getsize(output_path)} bytes")


def test_audio_storage():
    """Test the audio storage system by creating sample files"""
    
    base_dir = Path(__file__).parent.parent / "media" / "audio"
    test_room_id = "06e07d713c45"
    
    # Create test room directory
    room_dir = base_dir / test_room_id
    room_dir.mkdir(parents=True, exist_ok=True)
    
    # Create several test audio segments
    test_segments = [
        {"segment_id": 1, "language": "en", "duration": 3.0},
        {"segment_id": 2, "language": "en", "duration": 4.0}, 
        {"segment_id": 3, "language": "en", "duration": 2.5},
        {"segment_id": 1, "language": "th", "duration": 3.2},
        {"segment_id": 2, "language": "th", "duration": 4.1},
    ]
    
    print(f"Creating test audio files in: {room_dir}")
    print("=" * 60)
    
    for segment in test_segments:
        filename = f"{segment['segment_id']:06d}_{segment['language']}.wav"
        file_path = room_dir / filename
        
        create_test_audio_file(
            str(file_path), 
            duration_seconds=segment['duration']
        )
    
    print("=" * 60)
    print(f"✓ Created {len(test_segments)} test audio files")
    
    # List created files
    print("\nCreated files:")
    for file_path in sorted(room_dir.glob("*.wav")):
        size_kb = os.path.getsize(file_path) / 1024
        print(f"  {file_path.name} ({size_kb:.1f} KB)")


if __name__ == "__main__":
    print("Testing Audio Storage System")
    print("=" * 60)
    test_audio_storage()
    print("\n✅ Test completed successfully!")