#!/usr/bin/env python3
"""
Hebrew Transcription Tool using OpenAI Whisper
Optimized for Hebrew with ivrit-ai's fine-tuned models

For best Hebrew accuracy, use the ivrit-ai models which are specifically
trained on 295+ hours of Hebrew speech data.

Features:
- Hebrew-optimized transcription with ivrit-ai models
- Speaker diarization (who said what) with pyannote
- Timestamps and file output
"""

import argparse
import os
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

try:
    from pyannote.audio import Pipeline as DiarizationPipeline
    import torch
    PYANNOTE_AVAILABLE = True
except ImportError:
    PYANNOTE_AVAILABLE = False


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


def run_diarization(audio_path: str, hf_token: str = None, num_speakers: int = None) -> list:
    """
    Run speaker diarization to identify who spoke when.
    
    Args:
        audio_path: Path to the audio file
        hf_token: HuggingFace token (required for pyannote models)
        num_speakers: Optional number of speakers (auto-detect if None)
    
    Returns:
        List of (start, end, speaker) tuples
    """
    if not PYANNOTE_AVAILABLE:
        raise ImportError("pyannote.audio not installed. Run: pip install pyannote.audio")
    
    # Get token from argument or environment
    token = hf_token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGINGFACE_TOKEN")
    
    if not token:
        raise ValueError(
            "HuggingFace token required for speaker diarization.\n"
            "Get a token at: https://huggingface.co/settings/tokens\n"
            "Then either:\n"
            "  1. Set HF_TOKEN environment variable: export HF_TOKEN=your_token\n"
            "  2. Pass --hf-token your_token\n\n"
            "Note: You must also accept the model terms at:\n"
            "  https://huggingface.co/pyannote/speaker-diarization-3.1"
        )
    
    print("🔄 Loading speaker diarization model...")
    
    # Load pyannote diarization pipeline
    pipeline = DiarizationPipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=token
    )
    
    # Use GPU if available
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    pipeline.to(device)
    
    print(f"👥 Identifying speakers in: {audio_path}")
    
    # Run diarization
    if num_speakers:
        diarization = pipeline(audio_path, num_speakers=num_speakers)
    else:
        diarization = pipeline(audio_path)
    
    # Extract speaker segments
    speaker_segments = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        speaker_segments.append({
            "start": turn.start,
            "end": turn.end,
            "speaker": speaker
        })
    
    return speaker_segments


def transcribe_with_diarization(
    audio_path: str,
    model_name: str = "ivrit-ai/whisper-large-v3-turbo-ct2",
    beam_size: int = 5,
    hf_token: str = None,
    num_speakers: int = None,
) -> dict:
    """
    Transcribe with speaker diarization (who said what).
    
    Combines faster-whisper transcription with pyannote speaker diarization.
    """
    if not FASTER_WHISPER_AVAILABLE:
        raise ImportError("faster-whisper not installed. Run: pip install faster-whisper")
    
    # Step 1: Run diarization
    speaker_segments = run_diarization(audio_path, hf_token, num_speakers)
    
    # Count unique speakers
    unique_speakers = set(seg["speaker"] for seg in speaker_segments)
    print(f"👥 Found {len(unique_speakers)} speakers")
    
    # Step 2: Transcribe with word timestamps
    print(f"🔄 Loading faster-whisper model: {model_name}...")
    model = faster_whisper.WhisperModel(
        model_name,
        device="cpu",
        compute_type="int8",
    )
    
    print(f"🎙️ Transcribing: {audio_path}")
    segments, info = model.transcribe(
        audio_path,
        language="he",
        beam_size=beam_size,
        word_timestamps=True,
    )
    segments = list(segments)
    
    # Step 3: Assign speakers to transcription segments
    print("🔄 Matching speakers to text...")
    results = []
    
    for segment in segments:
        segment_mid = (segment.start + segment.end) / 2
        
        # Find speaker at midpoint
        speaker = "UNKNOWN"
        for diar_seg in speaker_segments:
            if diar_seg["start"] <= segment_mid <= diar_seg["end"]:
                speaker = diar_seg["speaker"]
                break
        
        results.append({
            "speaker": speaker,
            "start": segment.start,
            "end": segment.end,
            "text": segment.text.strip(),
        })
    
    return {
        "segments": results,
        "text": " ".join(seg["text"] for seg in results),
        "language": info.language,
        "language_probability": info.language_probability,
        "num_speakers": len(unique_speakers),
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
    
    # Choose transcription method
    if args.diarize:
        # Speaker diarization mode
        if not PYANNOTE_AVAILABLE:
            print("❌ Error: pyannote.audio not installed.")
            print("   Install with: pip install pyannote.audio")
            sys.exit(1)
        
        if not FASTER_WHISPER_AVAILABLE:
            print("❌ Error: faster-whisper not installed.")
            print("   Install with: pip install faster-whisper")
            sys.exit(1)
        
        try:
            result = transcribe_with_diarization(
                str(audio_path),
                model_name="ivrit-ai/whisper-large-v3-turbo-ct2",
                beam_size=args.beam_size,
                hf_token=args.hf_token,
                num_speakers=args.num_speakers,
            )
        except ValueError as e:
            print(f"❌ Error: {e}")
            sys.exit(1)
    
    elif args.ivrit:
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
