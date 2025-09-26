#!/usr/bin/env python3
"""
Minimal test server for Thai TTS timeline integration without database dependencies
"""

from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import json
import uuid
import asyncio
import time
import base64
import os
from pathlib import Path

# Create FastAPI app
app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# Mock settings
MEDIA_STORAGE_PATH = Path("media/audio")
MEDIA_STORAGE_PATH.mkdir(exist_ok=True, parents=True)

# Mock session storage
sessions = {}

@app.get("/")
async def serve_homepage():
    """Serve the main frontend page"""
    with open("frontend/index.html", "r") as f:
        content = f.read()
    return HTMLResponse(content=content)

@app.get("/room/{room_id}")
async def serve_room_page(room_id: str):
    """Serve the room page"""
    with open("frontend/room.html", "r") as f:
        content = f.read()
    return HTMLResponse(content=content)

@app.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """WebSocket endpoint for transcription and Thai TTS"""
    await websocket.accept()
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        'websocket': websocket,
        'created_at': time.time(),
        'transcript_segments': []
    }
    
    print(f"WebSocket connection established: {session_id}")
    
    try:
        while True:
            # Wait for messages from client
            message = await websocket.receive()
            
            if 'text' in message:
                # Handle JSON control messages
                try:
                    data = json.loads(message['text'])
                    if data.get('type') == 'control':
                        action = data.get('action')
                        if action == 'clear':
                            sessions[session_id]['transcript_segments'] = []
                            await websocket.send_text(json.dumps({
                                'type': 'status',
                                'message': 'Transcript cleared'
                            }))
                        elif action == 'get_thai_audio':
                            # Mock Thai TTS response
                            text = data.get('text', '')
                            if text:
                                # Generate mock Thai audio (silence)
                                mock_audio = b'\x00' * 8000  # 1 second of silence at 8kHz
                                audio_b64 = base64.b64encode(mock_audio).decode('utf-8')
                                
                                await websocket.send_text(json.dumps({
                                    'type': 'thai_audio',
                                    'text': text,
                                    'audio_data': audio_b64,
                                    'format': 'wav',
                                    'sample_rate': 8000
                                }))
                except json.JSONDecodeError:
                    pass
            
            elif 'bytes' in message:
                # Handle binary audio data
                audio_data = message['bytes']
                
                # Mock transcription response
                mock_transcript = {
                    'type': 'final',
                    'english': 'This is a test English transcript.',
                    'thai': 'นี่คือการทดสอบสำเนาภาษาอังกฤษ',
                    'confidence': 0.95,
                    'timestamp_ms': int(time.time() * 1000)
                }
                
                # Store in session
                sessions[session_id]['transcript_segments'].append(mock_transcript)
                
                await websocket.send_text(json.dumps(mock_transcript))
                
                # Simulate delay
                await asyncio.sleep(0.1)
                
    except Exception as e:
        print(f"WebSocket error for session {session_id}: {e}")
    finally:
        # Clean up session
        if session_id in sessions:
            del sessions[session_id]
        print(f"WebSocket connection closed: {session_id}")

@app.post("/api/audio/render")
async def render_final_audio_files(request_data: dict):
    """Mock endpoint for rendering final audio files"""
    room_id = request_data.get('room_id')
    
    if not room_id:
        raise HTTPException(status_code=400, detail="Room ID required")
    
    # Mock response
    return {
        'status': 'success',
        'files': {
            'english': f'media/audio/{room_id}_final_english.wav',
            'thai': f'media/audio/{room_id}_final_thai.wav'
        },
        'statistics': {
            'english_segments': 5,
            'thai_segments': 5,
            'total_duration': 45.2
        }
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)