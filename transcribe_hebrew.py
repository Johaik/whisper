#!/usr/bin/env python3
"""
Hebrew Transcription Tool using OpenAI Whisper
Optimized for Hebrew with ivrit-ai's fine-tuned models
"""

import argparse
import os
import sys
from pathlib import Path

# Add current directory to path so we can import app
sys.path.append(str(Path(__file__).parent))

# Import app modules
try:
    from app.config import get_settings
    from app.processors.transcribe import transcribe_audio
    from app.processors.diarize import diarize_audio, assign_speakers_to_transcript, HAS_DIARIZE_DEPS
except ImportError as e:
    print(f"❌ Error importing app modules: {e}")
    sys.exit(1)

# Check availability of faster-whisper (needed for app.processors.transcribe)
try:
    import faster_whisper
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False

# Check availability of openai-whisper (for fallback)
try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False


def transcribe_with_whisper(
    audio_path: str,
    model_size: str = "large",
    beam_size: int = 5,
    best_of: int = 5,
    temperature: float = 0.0,
    initial_prompt: str = None,
) -> dict:
    """
    Transcribe Hebrew audio using original Whisper.
    
    Args:
        audio_path: Path to the audio file
        model_size: Model size (large recommended for Hebrew)
        beam_size: Beam size for decoding
        best_of: Number of candidates when sampling
        temperature: Sampling temperature (0 = greedy/deterministic)
        initial_prompt: Optional prompt to guide transcription style
    
    Returns:
        Dictionary containing transcription results
    """
    print(f"🔄 Loading Whisper '{model_size}' model...")
    model = whisper.load_model(model_size)
    
    print(f"🎙️ Transcribing: {audio_path}")
    
    # Hebrew-optimized transcription parameters
    result = model.transcribe(
        audio_path,
        language="he",
        task="transcribe",
        
        # Decoding parameters for better accuracy
        beam_size=beam_size,           # Higher = more accurate (default 5)
        best_of=best_of,               # Number of candidates when sampling
        temperature=temperature,        # 0 = deterministic/greedy decoding
        
        # Compression and silence handling
        compression_ratio_threshold=2.4,  # Discard if too repetitive
        logprob_threshold=-1.0,           # Skip low probability tokens
        no_speech_threshold=0.6,          # Threshold for silence detection
        
        # Condition on previous text for consistency
        condition_on_previous_text=True,
        
        # Optional: Hebrew prompt to help with style/context
        initial_prompt=initial_prompt,
        
        verbose=False,
    )
    
    return result


def format_result(transcription_result) -> dict:
    """Convert TranscriptionResult object to dictionary format."""
    segments = []
    for seg in transcription_result.segments:
        segment_dict = {
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
        }
        if seg.speaker:
            segment_dict["speaker"] = seg.speaker
        segments.append(segment_dict)
        
    return {
        "text": transcription_result.text,
        "segments": segments,
        "language": transcription_result.language,
        "language_probability": transcription_result.language_probability,
        # Helper for printing stats
        "num_speakers": len(set(s.speaker for s in transcription_result.segments if s.speaker)) if any(s.speaker for s in transcription_result.segments) else 0
    }


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe Hebrew audio with optimized settings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Best accuracy with ivrit-ai Hebrew model (requires faster-whisper)
  python transcribe_hebrew.py audio.mp3 --ivrit
  
  # Speaker diarization (who said what) - requires HF_TOKEN
  export HF_TOKEN=your_huggingface_token
  python transcribe_hebrew.py call.m4a --diarize
  
  # Diarization with known number of speakers
  python transcribe_hebrew.py call.m4a --diarize --num-speakers 2
  
  # Using original Whisper with large model
  python transcribe_hebrew.py audio.mp3 --model large
  
  # Save to file
  python transcribe_hebrew.py audio.mp3 --ivrit --output result.txt

Recommended for Hebrew:
  --ivrit              Use ivrit-ai's Hebrew-trained model (BEST accuracy)
  --diarize            Separate speakers (caller vs callee)
  --beam-size 5-10     Higher beam size = more accurate
        """
    )
    
    parser.add_argument(
        "audio",
        type=str,
        help="Path to the audio file to transcribe"
    )
    parser.add_argument(
        "--ivrit",
        action="store_true",
        help="Use ivrit-ai's Hebrew-trained model (recommended, requires faster-whisper)"
    )
    parser.add_argument(
        "--model", "-m",
        type=str,
        default="large",
        choices=["tiny", "base", "small", "medium", "large", "large-v2", "large-v3", "turbo"],
        help="Whisper model size (default: large, recommended: large or large-v3)"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default=None,
        help="Output file path (optional)"
    )
    parser.add_argument(
        "--beam-size", "-b",
        type=int,
        default=5,
        help="Beam size for decoding (higher=more accurate, default: 5)"
    )
    parser.add_argument(
        "--no-vad",
        action="store_true",
        help="Disable voice activity detection (faster-whisper only)"
    )
    parser.add_argument(
        "--prompt", "-p",
        type=str,
        default=None,
        help="Initial prompt to guide transcription (e.g., punctuation style, names)"
    )
    parser.add_argument(
        "--translate", "-t",
        action="store_true",
        help="Translate Hebrew to English instead of transcribing"
    )
    parser.add_argument(
        "--timestamps",
        action="store_true",
        help="Include timestamps in output"
    )
    parser.add_argument(
        "--diarize",
        action="store_true",
        help="Enable speaker diarization (identify who said what)"
    )
    parser.add_argument(
        "--hf-token",
        type=str,
        default=None,
        help="HuggingFace token for pyannote (or set HF_TOKEN env var)"
    )
    parser.add_argument(
        "--num-speakers",
        type=int,
        default=None,
        help="Number of speakers (auto-detect if not specified)"
    )
    
    args = parser.parse_args()
    
    # Check if audio file exists
    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"❌ Error: Audio file not found: {args.audio}")
        sys.exit(1)

    # Set environment variables for settings
    if args.hf_token:
        os.environ["HUGGINGFACE_TOKEN"] = args.hf_token

    # Ensure diarization is enabled if requested
    if args.diarize:
        os.environ["DIARIZATION_ENABLED"] = "true"

    # Clear settings cache to pick up new env vars
    get_settings.cache_clear()
    
    # Choose transcription method
    if args.diarize:
        # Speaker diarization mode
        if not HAS_DIARIZE_DEPS:
            print("❌ Error: pyannote.audio/torch/torchaudio not installed.")
            print("   Install with: pip install -r requirements-ml.txt")
            sys.exit(1)
        
        if not FASTER_WHISPER_AVAILABLE:
            print("❌ Error: faster-whisper not installed.")
            print("   Install with: pip install faster-whisper")
            sys.exit(1)
        
        try:
            # 1. Diarize
            print("🔄 Running speaker diarization...")
            diarization_result = diarize_audio(str(audio_path), num_speakers=args.num_speakers)
            print(f"👥 Found {diarization_result.speaker_count} speakers")

            # 2. Transcribe
            # Note: We hardcode ivrit-ai model here as in original script, unless user overrides?
            # Original script: model_name="ivrit-ai/whisper-large-v3-turbo-ct2"
            model_name = "ivrit-ai/whisper-large-v3-turbo-ct2"

            print(f"🔄 Transcribing with faster-whisper model: {model_name}...")
            transcription_result = transcribe_audio(
                str(audio_path),
                model_name=model_name,
                beam_size=args.beam_size,
                vad_filter=not args.no_vad,
                initial_prompt=args.prompt,
                language="he",
            )

            # 3. Assign speakers
            print("🔄 Matching speakers to text...")
            transcription_result.segments = assign_speakers_to_transcript(
                transcription_result.segments,
                diarization_result
            )

            result = format_result(transcription_result)

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    elif args.ivrit:
        if not FASTER_WHISPER_AVAILABLE:
            print("❌ Error: faster-whisper not installed.")
            print("   Install with: pip install faster-whisper")
            sys.exit(1)
        
        try:
            print(f"🔄 Transcribing with ivrit-ai model...")
            transcription_result = transcribe_audio(
                str(audio_path),
                model_name="ivrit-ai/whisper-large-v3-turbo-ct2",
                beam_size=args.beam_size,
                vad_filter=not args.no_vad,
                initial_prompt=args.prompt,
                language="he",
            )
            result = format_result(transcription_result)
        except Exception as e:
            print(f"❌ Error: {e}")
            sys.exit(1)

    else:
        if not WHISPER_AVAILABLE:
            print("❌ Error: openai-whisper not installed.")
            print("   Install with: pip install openai-whisper")
            sys.exit(1)
        
        # For translation, we need original whisper (or if using other models without faster-whisper)
        if args.translate:
            print("🔄 Loading Whisper for translation...")
            model = whisper.load_model(args.model)
            result = model.transcribe(
                str(audio_path),
                language="he",
                task="translate",
                beam_size=args.beam_size,
                verbose=False,
            )
        else:
            result = transcribe_with_whisper(
                str(audio_path),
                model_size=args.model,
                beam_size=args.beam_size,
                initial_prompt=args.prompt,
            )
    
    # Format output
    text = result["text"].strip()
    
    if args.diarize and result.get("segments"):
        # Diarization output with speaker labels
        output_lines = []
        for seg in result["segments"]:
            speaker = seg.get("speaker", "UNKNOWN")
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            seg_text = seg.get("text", "").strip()
            if args.timestamps:
                output_lines.append(f"[{speaker}] [{start:.2f} -> {end:.2f}] {seg_text}")
            else:
                output_lines.append(f"[{speaker}] {seg_text}")
        output_text = "\n".join(output_lines)
    elif args.timestamps and result.get("segments"):
        output_lines = []
        for seg in result["segments"]:
            start = seg.get("start", 0)
            end = seg.get("end", 0)
            seg_text = seg.get("text", "").strip()
            output_lines.append(f"[{start:.2f} -> {end:.2f}] {seg_text}")
        output_text = "\n".join(output_lines)
    else:
        output_text = text
    
    # Save or print output
    if args.output:
        output_path = Path(args.output)
        output_path.write_text(output_text, encoding="utf-8")
        print(f"✅ Saved to: {args.output}")
    else:
        print("\n" + "=" * 60)
        print("📝 Transcription Result:")
        print("=" * 60)
        print(output_text)
        print("=" * 60)
    
    # Print stats
    if result.get("segments"):
        print(f"\n📊 Detected {len(result['segments'])} segments")
    if result.get("num_speakers"):
        print(f"👥 Speakers identified: {result['num_speakers']}")
    if result.get("language_probability"):
        print(f"🔤 Language confidence: {result['language_probability']:.1%}")


if __name__ == "__main__":
    main()
