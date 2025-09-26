#!/usr/bin/env python3
"""
Test persistent presenter-client subtitle flow
"""
import asyncio
import websockets
import json
import time

async def test_persistent_flow():
    """Test with persistent presenter connection and subtitle broadcasting"""
    
    presenter_uri = 'ws://localhost:8000/ws/transcribe'
    client_uri = 'ws://localhost:8000/ws/room/test123'
    
    print("🎯 Testing persistent presenter-client flow...")
    
    # Connect presenter WebSocket
    print("📡 Connecting presenter...")
    presenter_ws = await websockets.connect(presenter_uri)
    print("✅ Presenter connected")
    
    try:
        # Wait for session message
        session_msg = await asyncio.wait_for(presenter_ws.recv(), timeout=5)
        session_data = json.loads(session_msg)
        session_id = session_data['sessionId']
        print(f"📨 Presenter session: {session_id}")
        
        # Send config to link with room
        config = {
            'type': 'config',
            'roomId': 'test123',
            'sampleRate': 16000
        }
        await presenter_ws.send(json.dumps(config))
        print(f"📤 Sent config for room test123")
        
        # Wait for config response
        config_response = await asyncio.wait_for(presenter_ws.recv(), timeout=5)
        print(f"📨 Config response: {json.loads(config_response)}")
        
        # Give time for auto-linking
        await asyncio.sleep(2)
        
        # Connect client WebSocket
        print("👥 Connecting client...")
        client_ws = await websockets.connect(client_uri)
        print("✅ Client connected")
        
        # Wait for initial room status
        room_msg = await asyncio.wait_for(client_ws.recv(), timeout=5)
        room_data = json.loads(room_msg)
        print(f"📨 Client received room status: {room_data}")
        
        # Simulate subtitle broadcasting by sending audio data to presenter
        print("🎤 Simulating presenter transcription...")
        
        # Send some dummy audio data to trigger transcription
        dummy_audio = b'\\x00' * 1600  # 0.1 seconds of silence at 16kHz
        
        for i in range(3):
            print(f"📡 Sending audio chunk {i+1}...")
            await presenter_ws.send(dummy_audio)
            
            # Check if client receives anything
            try:
                client_response = await asyncio.wait_for(client_ws.recv(), timeout=3)
                client_data = json.loads(client_response)
                print(f"✅ Client received: {client_data}")
            except asyncio.TimeoutError:
                print("⏰ No client response within timeout")
            
            await asyncio.sleep(1)
        
        print("🔄 Keeping connections alive for 10 seconds...")
        await asyncio.sleep(10)
        
        print("🎉 Test completed!")
        
    finally:
        print("🔌 Closing connections...")
        await presenter_ws.close()
        await client_ws.close()

if __name__ == "__main__":
    asyncio.run(test_persistent_flow())