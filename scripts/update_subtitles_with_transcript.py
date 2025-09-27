#!/usr/bin/env python3
"""
Script to update recovered subtitle segments with actual transcript content.
"""

import sys
import asyncio
from pathlib import Path
import re

# Add the backend directory to Python path
sys.path.append('/app/backend')

from backend.db_service import AsyncDatabaseService


async def update_subtitles_with_transcript(room_id: str, transcript_file: str):
    """Update recovered subtitle segments with actual transcript content."""
    
    print(f"🔄 Updating subtitles for room: {room_id}")
    print(f"📄 Using transcript file: {transcript_file}")
    
    # Read and parse transcript file
    transcript_entries = []
    
    try:
        with open(transcript_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Parse transcript entries
        lines = content.split('\n')
        segment_number = 1
        
        for line in lines:
            # Look for pattern: [timestamp] Thai text (EN: English text)
            if line.startswith('[') and ']' in line:
                try:
                    # Extract text part after timestamp
                    text_part = line[line.index(']') + 1:].strip()
                    
                    # Parse text content
                    if ' (EN: ' in text_part and text_part.endswith(')'):
                        thai_text = text_part[:text_part.index(' (EN:')].strip()
                        english_text = text_part[text_part.index(' (EN:') + 5:-1].strip()
                    else:
                        # If no English translation, use the text as both
                        thai_text = text_part
                        english_text = text_part
                    
                    transcript_entries.append({
                        'segment_number': segment_number,
                        'thai': thai_text,
                        'english': english_text
                    })
                    
                    segment_number += 1
                    
                except (ValueError, IndexError) as e:
                    print(f"⚠️  Error parsing line: {line[:50]}... - {e}")
                    continue
        
        print(f"📝 Parsed {len(transcript_entries)} transcript entries")
        
        # Update database entries
        updated_count = 0
        
        for entry in transcript_entries:
            segment_id = f"{entry['segment_number']:06d}"
            
            try:
                # Update the existing subtitle segment
                await AsyncDatabaseService.update_subtitle_segment_text(
                    room_id=room_id,
                    segment_id=segment_id,
                    text_en=entry['english'],
                    text_th=entry['thai']
                )
                
                updated_count += 1
                
                if updated_count % 10 == 0:
                    print(f"✅ Updated {updated_count} segments...")
                    
            except Exception as e:
                print(f"❌ Error updating segment {segment_id}: {e}")
        
        print(f"🎉 Update completed! Updated {updated_count} subtitle segments")
        return True
        
    except Exception as e:
        print(f"❌ Error reading transcript file: {e}")
        return False


async def main():
    if len(sys.argv) < 3:
        print("Usage: python update_subtitles_with_transcript.py <room_id> <transcript_file>")
        sys.exit(1)
    
    room_id = sys.argv[1]
    transcript_file = sys.argv[2]
    
    success = await update_subtitles_with_transcript(room_id, transcript_file)
    if success:
        print("✨ Subtitle update completed successfully!")
    else:
        print("💥 Subtitle update failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())