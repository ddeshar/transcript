#!/usr/bin/env python3
"""
Test script to simulate subtitle broadcasting to verify client interface
"""
import asyncio
import websockets
import json
import time

async def test_presenter_client_flow():
    """Test subtitle flow from presenter to client"""
    
    # Connect as presenter
    presenter_uri = 'ws://localhost:8000/ws/transcribe'
    client_uri = 'ws://localhost:8000/ws/room/test123'
    
    try:
        print("🎯 Testing subtitle broadcast flow...")
        
        # Connect presenter WebSocket
        print("📡 Connecting presenter...")
        async with websockets.connect(presenter_uri) as presenter_ws:
            print("✅ Presenter connected")
            
            # Wait for session message
            session_msg = await asyncio.wait_for(presenter_ws.recv(), timeout=5)
            session_data = json.loads(session_msg)
            print(f"📨 Presenter received: {session_data}")
            
            # Connect client WebSocket
            print("👥 Connecting client...")
            async with websockets.connect(client_uri) as client_ws:
                print("✅ Client connected")
                
                # Wait for initial room status
                room_msg = await asyncio.wait_for(client_ws.recv(), timeout=5)
                room_data = json.loads(room_msg)
                print(f"📨 Client received room status: {room_data}")
                
                # Simulate subtitle data from presenter
                test_subtitles = [
                    {
                        "type": "partial",
                        "english": "Hello world",
                        "thai": "สวัสดีโลก",
                        "timestamp_ms": int(time.time() * 1000)
                    },
                    {
                        "type": "final", 
                        "english": "Hello world, this is a test",
                        "thai": "สวัสดีโลก นี่คือการทดสอบ",
                        "timestamp_ms": int(time.time() * 1000)
                    }
                ]
                
                print("🎤 Simulating presenter audio...")
                for subtitle in test_subtitles:
                    print(f"📡 Broadcasting: {subtitle}")
                    
                    # Send to presenter (simulate transcription result)
                    await presenter_ws.send(json.dumps(subtitle))
                    
                    # Check if client receives the broadcast
                    try:
                        client_response = await asyncio.wait_for(client_ws.recv(), timeout=2)
                        client_data = json.loads(client_response)
                        print(f"✅ Client received: {client_data}")
                    except asyncio.TimeoutError:
                        print("⏰ Client didn't receive subtitle within timeout")
                    
                    await asyncio.sleep(1)
                
                print("🎉 Test completed!")
                
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_presenter_client_flow())