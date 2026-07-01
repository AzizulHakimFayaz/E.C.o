import os
import asyncio
import tempfile
import speech_recognition as sr
import pygame
import edge_tts
import re
from memory.config import load_config

# Initialize pygame mixer
try:
    pygame.mixer.init()
except Exception as e:
    print(f"⚠️ Warning: Could not initialize pygame mixer: {e}")

def get_voice_settings():
    config = load_config()
    voice_name = config.get("voice_name", "en-US-AriaNeural")
    return voice_name

async def _save_speech(text: str, voice: str, filepath: str):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(filepath)

def speak(text: str):
    """
    Synthesizes the text using Microsoft Edge Neural TTS and plays it using pygame.
    """
    if not text or not text.strip():
        return
        
    voice = get_voice_settings()
    
    # Clean up text for TTS (remove code blocks, markdown links, asterisks, JSON tool calls)
    clean_text = re.sub(r'```.*?```', '[code block]', text, flags=re.DOTALL)
    clean_text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', clean_text)
    clean_text = re.sub(r'\*+', '', clean_text)
    clean_text = re.sub(r'\{.*?"tool".*?\}', '', clean_text, flags=re.DOTALL)
    clean_text = clean_text.strip()
    
    if not clean_text:
        return
        
    temp_dir = tempfile.gettempdir()
    temp_file = os.path.join(temp_dir, "eco_response.mp3")
    
    # Clean up old file if it exists
    if os.path.exists(temp_file):
        try:
            os.remove(temp_file)
        except Exception:
            pass
            
    # Generate MP3
    try:
        asyncio.run(_save_speech(clean_text, voice, temp_file))
    except Exception as e:
        print(f"\n❌ [Voice Output] TTS Generation failed: {e}")
        return

    # Play MP3
    try:
        pygame.mixer.music.load(temp_file)
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            pygame.time.Clock().tick(10)
        pygame.mixer.music.unload()
    except Exception as e:
        print(f"\n❌ [Voice Output] Audio playback failed: {e}")
        
    # Clean up temporary file
    try:
        os.remove(temp_file)
    except Exception:
        pass

def listen(timeout=10, phrase_time_limit=15) -> str:
    """
    Listens to the microphone and transcribes user speech.
    """
    r = sr.Recognizer()
    r.dynamic_energy_threshold = True
    
    try:
        with sr.Microphone() as source:
            print("\n🎤 Listening... (speak now or press Ctrl+C to cancel)")
            try:
                r.adjust_for_ambient_noise(source, duration=0.8)
                audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
            except sr.WaitTimeoutError:
                print("⏳ Listening timed out. No speech detected.")
                return ""
            except KeyboardInterrupt:
                print("\n❌ Listening cancelled.")
                raise
            except Exception as e:
                print(f"\n❌ Microphone record error: {e}")
                return ""
    except Exception as e:
        print(f"\n❌ Microphone initialization error: {e}")
        print("Please check if you have a microphone connected and recording permissions enabled.")
        return ""
            
    print("⏳ Transcribing speech...")
    try:
        text = r.recognize_google(audio)
        print(f"You (Voice): {text}")
        return text
    except sr.UnknownValueError:
        print("🤷 Speech could not be understood.")
        return ""
    except sr.RequestError as e:
        print(f"❌ Speech Recognition service error: {e}")
        return ""
