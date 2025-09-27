#!/usr/bin/env python3
"""
Script to recover subtitle segments for a room from transcript files and audio files.
This script reconstructs the database entries when the original session wasn't properly linked.
"""

import os
import sys
import json
import asyncio
from datetime import datetime, timedelta
from pathlib import Path

# Add the backend directory to Python path
sys.path.append(str(Path(__file__).parent.parent / "backend"))
sys.path.append('/app/backend')

from backend.db_service import AsyncDatabaseService
from backend.database import get_db, SubtitleSegment


async def recover_room_subtitles(room_id: str, audio_dir: str, transcript_files: list):
    """Recover subtitle segments for a room from available data."""
    
    print(f"🔄 Starting recovery for room: {room_id}")
    
    # Check if room exists
    room = await AsyncDatabaseService.get_room(room_id)
    if not room:
        print(f"❌ Room {room_id} not found in database")
        return False
    
    # Check existing subtitle count
    existing_segments = await AsyncDatabaseService.get_room_subtitle_segments(room_id)
    if existing_segments:
        print(f"⚠️  Room already has {len(existing_segments)} subtitle segments")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            return False
    
    # Scan audio files to determine segment count
    audio_path = Path(audio_dir) / room_id
    if not audio_path.exists():
        print(f"❌ Audio directory not found: {audio_path}")
        return False
    
    # Get all audio files and extract segment info
    audio_files = []
    for file in sorted(audio_path.glob("*.wav")):
        # Parse filename: {segment_id:06d}_{language}.wav
        if "_" in file.stem:
            segment_id_str, language = file.stem.split("_", 1)
            try:
                segment_id = int(segment_id_str)
                audio_files.append({
                    'segment_id': segment_id,
                    'language': language,
                    'filename': file.name,
                    'path': str(file)
                })
            except ValueError:
                continue
    
    if not audio_files:
        print(f"❌ No valid audio files found in {audio_path}")
        return False
    
    print(f"📁 Found {len(audio_files)} audio files")
    
    # Group by segment ID
    segments_by_id = {}
    for af in audio_files:
        seg_id = af['segment_id']
        if seg_id not in segments_by_id:
            segments_by_id[seg_id] = {}
        segments_by_id[seg_id][af['language']] = af
    
    # Try to parse transcript files for actual text content
    transcript_data = {}
    
    for transcript_file in transcript_files:
        try:
            with open(transcript_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse transcript entries
            lines = content.split('\n')
            for line in lines:
                # Look for pattern: [HH:MM:SS.mmm] Thai text (EN: English text)
                if line.startswith('[') and ']' in line:
                    try:
                        timestamp_part = line[1:line.index(']')]
                        text_part = line[line.index(']') + 1:].strip()
                        
                        # Parse timestamp
                        time_parts = timestamp_part.split(':')
                        if len(time_parts) == 3:
                            hours = int(time_parts[0])
                            minutes = int(time_parts[1])
                            seconds_ms = time_parts[2].split('.')
                            seconds = int(seconds_ms[0])
                            milliseconds = int(seconds_ms[1]) if len(seconds_ms) > 1 else 0
                            
                            total_ms = (hours * 3600 + minutes * 60 + seconds) * 1000 + milliseconds
                            
                            # Parse text content
                            if ' (EN: ' in text_part and text_part.endswith(')'):
                                thai_text = text_part[:text_part.index(' (EN:')].strip()
                                english_text = text_part[text_part.index(' (EN:') + 5:-1].strip()
                            else:
                                thai_text = text_part
                                english_text = text_part
                            
                            transcript_data[total_ms] = {
                                'thai': thai_text,
                                'english': english_text,
                                'timestamp_ms': total_ms
                            }
                    except (ValueError, IndexError):
                        continue
        except Exception as e:
            print(f"⚠️  Error parsing transcript file {transcript_file}: {e}")
    
    print(f"📝 Parsed {len(transcript_data)} transcript entries")
    
    # Create subtitle segments
    base_time = datetime.now()
    recovered_count = 0
    
    for segment_id in sorted(segments_by_id.keys()):
        # Estimate timestamp (5 seconds per segment)
        estimated_timestamp = int((base_time - timedelta(seconds=(max(segments_by_id.keys()) - segment_id) * 5)).timestamp() * 1000)
        
        # Try to find matching transcript entry
        thai_text = f"[Recovered Audio Segment {segment_id}]"
        english_text = f"[Recovered Audio Segment {segment_id}]"
        
        # Look for closest transcript entry
        closest_transcript = None
        min_time_diff = float('inf')
        
        for ts_ms, ts_data in transcript_data.items():
            time_diff = abs(ts_ms - estimated_timestamp)
            if time_diff < min_time_diff:
                min_time_diff = time_diff
                closest_transcript = ts_data
        
        # Use transcript text if found and reasonably close (within 10 seconds)
        if closest_transcript and min_time_diff < 10000:
            thai_text = closest_transcript['thai']
            english_text = closest_transcript['english']
            estimated_timestamp = closest_transcript['timestamp_ms']
        
        try:
            # Save subtitle segment to database
            await AsyncDatabaseService.save_subtitle_segment(
                room_id=room_id,
                segment_id=f"{segment_id:06d}",
                timestamp_ms=estimated_timestamp,
                duration_ms=5000,  # Estimate 5 seconds per segment
                sequence_number=segment_id,
                text_en=english_text,
                text_th=thai_text,
                confidence_en=0.85,  # Estimated confidence
                confidence_th=0.85,
                asr_provider="recovered",
                mt_provider="recovered",
                processing_time_ms=0,
                is_final=True
            )
            
            recovered_count += 1
            
            if recovered_count % 10 == 0:
                print(f"✅ Recovered {recovered_count} segments...")
                
        except Exception as e:
            print(f"❌ Error saving segment {segment_id}: {e}")
    
    print(f"🎉 Recovery completed! Recovered {recovered_count} subtitle segments for room {room_id}")
    return True


async def main():
    if len(sys.argv) < 2:
        print("Usage: python recover_room_subtitles.py <room_id> [audio_dir] [transcript_files...]")
        print("Example: python recover_room_subtitles.py e1b1cd3fcfa6 /app/media/audio ../subtitles/transcript_session_*.txt")
        sys.exit(1)
    
    room_id = sys.argv[1]
    audio_dir = sys.argv[2] if len(sys.argv) > 2 else "/app/media/audio"
    transcript_files = sys.argv[3:] if len(sys.argv) > 3 else []
    
    # If no transcript files specified, look for them
    if not transcript_files:
        subtitles_dir = Path(__file__).parent.parent / "subtitles"
        if subtitles_dir.exists():
            transcript_files = list(subtitles_dir.glob("transcript_session_*.txt"))
            transcript_files = [str(f) for f in transcript_files]
        
        print(f"📂 Found {len(transcript_files)} transcript files to check")
    
    success = await recover_room_subtitles(room_id, audio_dir, transcript_files)
    if success:
        print("✨ Subtitle recovery completed successfully!")
    else:
        print("💥 Subtitle recovery failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())