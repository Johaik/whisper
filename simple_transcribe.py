#!/usr/bin/env python3
"""
Simple Whisper transcription script.
Usage: python simple_transcribe.py audio_file.mp3
"""

import sys
import whisper


def transcribe(audio_path: str, model_name: str = "base") -> str:
    """Transcribe an audio file using Whisper."""
    print(f"Loading model: {model_name}...")
    model = whisper.load_model(model_name)
    
    print(f"Transcribing: {audio_path}...")
    result = model.transcribe(audio_path)
    
    return result["text"]


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python simple_transcribe.py <audio_file> [model]")
        print("Models: tiny, base, small, medium, large")
        sys.exit(1)
    
    audio_file = sys.argv[1]
    model = sys.argv[2] if len(sys.argv) > 2 else "base"
    
    text = transcribe(audio_file, model)
    print("\n--- Transcription ---")
    print(text)
