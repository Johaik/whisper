#!/usr/bin/env python3
"""
Hebrew Transcription Tool using OpenAI Whisper
Optimized for Hebrew with ivrit-ai's fine-tuned models

For best Hebrew accuracy, use the ivrit-ai models which are specifically
trained on 295+ hours of Hebrew speech data.
"""

import argparse
import sys
from pathlib import Path

# Check which library is available
try:
    import faster_whisper
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False

try:
    import whisper
    WHISPER_AVAILABLE = True
except ImportError:
    WHISPER_AVAILABLE = False


def transcribe_with_faster_whisper(
    audio_path: str,
    model_name: str = "ivrit-ai/whisper-large-v3-turbo-ct2",
    beam_size: int = 5,
    vad_filter: bool = True,
) -> dict:
    """
    Transcribe Hebrew audio using faster-whisper (recommended for speed).
    
    Args:
        audio_path: Path to the audio file
        model_name: Model name (ivrit-ai models recommended for Hebrew)
        beam_size: Beam size for decoding (higher = more accurate but slower)
        vad_filter: Use voice activity detection to filter out silence
    
    Returns:
        Dictionary containing transcription results
    """
    print(f"🔄 Loading faster-whisper model: {model_name}...")
    
    # Use CPU with int8 quantization for Mac, or GPU if available
    model = faster_whisper.WhisperModel(
        model_name,
        device="cpu",  # Use "cuda" if you have NVIDIA GPU
        compute_type="int8",  # Use "float16" for GPU
    )
    
    print(f"🎙️ Transcribing: {audio_path}")
    
    segments, info = model.transcribe(
        audio_path,
        language="he",
        beam_size=beam_size,
        vad_filter=vad_filter,  # Filter out silence
        vad_parameters=dict(
            min_silence_duration_ms=500,  # Minimum silence to split
        ),
    )
    
    # Collect all segments
    texts = []
    all_segments = []
    for segment in segments:
        texts.append(segment.text)
        all_segments.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
        })
    
    return {
        "text": " ".join(texts),
        "segments": all_segments,
        "language": info.language,
        "language_probability": info.language_probability,
    }


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


def main():
    parser = argparse.ArgumentParser(
        description="Transcribe Hebrew audio with optimized settings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Best accuracy with ivrit-ai Hebrew model (requires faster-whisper)
  python transcribe_hebrew.py audio.mp3 --ivrit
  
  # Using original Whisper with large model
  python transcribe_hebrew.py audio.mp3 --model large
  
  # High accuracy mode with beam search
  python transcribe_hebrew.py audio.mp3 --model large --beam-size 10
  
  # Save to file
  python transcribe_hebrew.py audio.mp3 --ivrit --output result.txt

Recommended for Hebrew:
  --ivrit              Use ivrit-ai's Hebrew-trained model (BEST accuracy)
  --model large        Use OpenAI's large model
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
    
    args = parser.parse_args()
    
    # Check if audio file exists
    audio_path = Path(args.audio)
    if not audio_path.exists():
        print(f"❌ Error: Audio file not found: {args.audio}")
        sys.exit(1)
    
    # Choose transcription method
    if args.ivrit:
        if not FASTER_WHISPER_AVAILABLE:
            print("❌ Error: faster-whisper not installed.")
            print("   Install with: pip install faster-whisper")
            sys.exit(1)
        
        result = transcribe_with_faster_whisper(
            str(audio_path),
            model_name="ivrit-ai/whisper-large-v3-turbo-ct2",
            beam_size=args.beam_size,
            vad_filter=not args.no_vad,
        )
    else:
        if not WHISPER_AVAILABLE:
            print("❌ Error: openai-whisper not installed.")
            print("   Install with: pip install openai-whisper")
            sys.exit(1)
        
        # For translation, we need original whisper
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
    
    if args.timestamps and result.get("segments"):
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
    if result.get("language_probability"):
        print(f"🔤 Language confidence: {result['language_probability']:.1%}")


if __name__ == "__main__":
    main()
