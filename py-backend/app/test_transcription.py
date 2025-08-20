# test_transcription.py - Run this to test your backend setup
import requests
import os
import io
import wave
import struct
import math

def create_test_audio():
    """Create a simple test audio file (sine wave) for testing"""
    # Audio parameters
    sample_rate = 16000
    duration = 2.0  # 2 seconds
    frequency = 440  # A note
    
    # Generate sine wave
    samples = int(sample_rate * duration)
    audio_data = []
    
    for i in range(samples):
        t = i / sample_rate
        sample = int(32767 * 0.5 * math.sin(2 * math.pi * frequency * t))
        audio_data.append(sample)
    
    # Create WAV file in memory
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 2 bytes per sample
        wav_file.setframerate(sample_rate)
        
        # Pack audio data
        packed_data = struct.pack('<' + 'h' * len(audio_data), *audio_data)
        wav_file.writeframes(packed_data)
    
    wav_buffer.seek(0)
    return wav_buffer.getvalue()

def test_backend():
    base_url = "http://localhost:8000"
    
    print("🧪 Testing FinAgent Backend with Transcription Support")
    print("=" * 60)
    
    # Test 1: Main health check
    print("\n1️⃣ Testing main health check...")
    try:
        response = requests.get(f"{base_url}/health")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
        print("   Make sure your FastAPI server is running: python app.py")
        return
    
    # Test 2: Root endpoint
    print("\n2️⃣ Testing root endpoint...")
    try:
        response = requests.get(f"{base_url}/")
        print(f"   Status: {response.status_code}")
        data = response.json()
        print(f"   Available endpoints: {list(data.get('endpoints', {}).keys())}")
        if 'transcription' in data.get('endpoints', {}):
            print("   ✅ Transcription endpoint found in root response")
        else:
            print("   ⚠️ Transcription endpoint not listed in root response")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 3: Transcription health check
    print("\n3️⃣ Testing transcription health check...")
    try:
        response = requests.get(f"{base_url}/api/transcribe/health")
        print(f"   Status: {response.status_code}")
        data = response.json()
        print(f"   Response: {data}")
        
        if response.status_code == 200 and data.get('status') == 'healthy':
            print("   ✅ Transcription service is healthy")
        elif data.get('error'):
            print(f"   ❌ Transcription service error: {data.get('error')}")
        else:
            print("   ⚠️ Transcription service status unclear")
            
    except Exception as e:
        print(f"   ❌ Error: {e}")
        if "404" in str(e):
            print("   💡 This suggests the transcription router is not properly included")
    
    # Test 4: Transcription info
    print("\n4️⃣ Testing transcription info endpoint...")
    try:
        response = requests.get(f"{base_url}/api/transcribe/info")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"   Provider: {data.get('provider')}")
            print(f"   Supported formats: {data.get('supported_formats')}")
            print("   ✅ Transcription info endpoint working")
        else:
            print("   ❌ Transcription info endpoint not working")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Test 5: OpenAI API Key check
    print("\n5️⃣ Checking OpenAI API Key...")
    openai_key = os.getenv('OPENAI_API_KEY')
    if openai_key:
        if openai_key.startswith('sk-'):
            print("   ✅ OpenAI API Key found and looks valid")
        else:
            print("   ⚠️ OpenAI API Key found but doesn't start with 'sk-'")
    else:
        print("   ❌ OpenAI API Key not found in environment")
        print("   💡 Set it with: export OPENAI_API_KEY='your-key-here'")
    
    # Test 6: Check FastAPI docs
    print("\n6️⃣ Testing FastAPI documentation...")
    try:
        response = requests.get(f"{base_url}/docs")
        if response.status_code == 200:
            print("   ✅ FastAPI docs available at http://localhost:8000/docs")
            print("   💡 Check the docs to see if 'Voice Transcription' section exists")
        else:
            print("   ❌ FastAPI docs not accessible")
    except Exception as e:
        print(f"   ❌ Error: {e}")

    # Test 7: POST test for actual transcription
    print("\n7️⃣ Testing actual transcription POST endpoint...")
    if not openai_key or not openai_key.startswith('sk-'):
        print("   ⏭️ Skipping transcription POST test - no valid OpenAI API key")
    else:
        try:
            print("   📝 Creating test audio file...")
            test_audio = create_test_audio()
            
            # Prepare the file for upload
            files = {
                'file': ('test_audio.wav', test_audio, 'audio/wav')
            }
            
            print("   🚀 Sending transcription request...")
            response = requests.post(f"{base_url}/api/transcribe", files=files)
            
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                try:
                    data = response.json()
                    print(f"   ✅ Transcription successful!")
                    print(f"   Text: '{data.get('text', 'No text returned')}'")
                    print(f"   Duration: {data.get('duration', 'Unknown')}s")
                    if data.get('confidence'):
                        print(f"   Confidence: {data.get('confidence')}")
                except ValueError:
                    print("   ⚠️ Response is not JSON format")
                    print(f"   Raw response: {response.text[:200]}...")
            elif response.status_code == 422:
                print("   ❌ Validation error - check file format")
                try:
                    error_detail = response.json()
                    print(f"   Detail: {error_detail}")
                except:
                    print(f"   Raw error: {response.text}")
            elif response.status_code == 500:
                print("   ❌ Server error - likely OpenAI API issue")
                try:
                    error_detail = response.json()
                    print(f"   Error: {error_detail.get('detail', 'Unknown server error')}")
                except:
                    print(f"   Raw error: {response.text}")
            else:
                print(f"   ❌ Unexpected status code: {response.status_code}")
                print(f"   Response: {response.text}")
                
        except Exception as e:
            print(f"   ❌ Error during POST test: {e}")
    
    # Test 8: Test with invalid file (to check error handling)
    print("\n8️⃣ Testing error handling with invalid file...")
    try:
        # Send a text file instead of audio
        files = {
            'file': ('test.txt', b'This is not an audio file', 'text/plain')
        }
        
        response = requests.post(f"{base_url}/api/transcribe", files=files)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 400 or response.status_code == 422:
            print("   ✅ Server correctly rejected invalid file format")
            try:
                error_data = response.json()
                print(f"   Error message: {error_data.get('detail', 'No detail')}")
            except:
                print(f"   Raw response: {response.text}")
        else:
            print(f"   ⚠️ Unexpected response to invalid file: {response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error during invalid file test: {e}")

    print("\n" + "=" * 60)
    print("🏁 Test Complete!")
    print("\nNext steps if there are issues:")
    print("1. Make sure transcription.py file exists in app/api_routes/")
    print("2. Check app.py has the transcription import and router include")
    print("3. Install missing dependencies: pip install openai python-multipart")
    print("4. Set OpenAI API key: export OPENAI_API_KEY='your-key-here'")
    print("5. Restart your FastAPI server: python app.py")
    print("6. Check server logs for detailed error messages")
    print("\nIf transcription works but returns unexpected text:")
    print("- The test audio is a simple sine wave tone")
    print("- OpenAI might transcribe it as silence or noise")
    print("- Try with a real audio file containing speech for better results")

if __name__ == "__main__":
    test_backend()
