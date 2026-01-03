# Hebrew Transcription with Whisper

A Hebrew speech-to-text transcription tool using [OpenAI's Whisper](https://github.com/openai/whisper) and [ivrit-ai's Hebrew-optimized models](https://huggingface.co/ivrit-ai).

## Quick Start

```bash
# Activate the virtual environment
source venv/bin/activate

# BEST: Use ivrit-ai's Hebrew-trained model (recommended!)
python transcribe_hebrew.py audio.mp3 --ivrit

# Alternative: Use OpenAI's large model
python transcribe_hebrew.py audio.mp3 --model large
```

## 🎯 Best Practices for Hebrew Accuracy

### 1. Use ivrit-ai's Hebrew-Trained Model (Recommended)

The `--ivrit` flag uses [ivrit-ai/whisper-large-v3-turbo-ct2](https://huggingface.co/ivrit-ai/whisper-large-v3-turbo-ct2), which is:
- **Fine-tuned on 295+ hours of Hebrew speech**
- **~3x faster** than standard Whisper (uses CTranslate2)
- **Much more accurate** for Hebrew than standard models

```bash
python transcribe_hebrew.py audio.mp3 --ivrit
```

### 2. Use Larger Models

Larger models = better accuracy for non-English languages:

```bash
# For standard Whisper (if not using --ivrit)
python transcribe_hebrew.py audio.mp3 --model large-v3
python transcribe_hebrew.py audio.mp3 --model large
```

### 3. Increase Beam Size

Higher beam size = more accurate (but slower):

```bash
python transcribe_hebrew.py audio.mp3 --ivrit --beam-size 10
```

### 4. Use Initial Prompts

Guide the model with context (names, punctuation style):

```bash
python transcribe_hebrew.py audio.mp3 --model large --prompt "שמות: יוחאי, דנה. פיסוק מלא."
```

### 5. Audio Quality

- **Don't preprocess**: Studies show noise reduction can *hurt* accuracy
- Use original audio when possible
- Clear recordings work best

## Comparison: ivrit-ai vs Standard Whisper

| Feature | Standard Whisper (base) | ivrit-ai Model |
|---------|------------------------|----------------|
| Hebrew Training | General multilingual | 295+ hours Hebrew |
| Speed | Slower | ~3x faster |
| Accuracy | Good | Excellent |
| Punctuation | Sometimes missing | Better |

**Example output comparison:**

Standard `base` model:
> אהלו שלום יוכי עלה נתאי מכלן שלום חי בסדר יום הוא כמו נשמע יופי...

ivrit-ai model:
> שלום יוחאי, מה שלומך? בסדר גמור, מה נשמח? יופי, בסדר גמור...

## Command Reference

```bash
# Best accuracy (ivrit-ai Hebrew model)
python transcribe_hebrew.py audio.mp3 --ivrit

# High accuracy mode
python transcribe_hebrew.py audio.mp3 --ivrit --beam-size 10

# Save to file
python transcribe_hebrew.py audio.mp3 --ivrit --output result.txt

# With timestamps
python transcribe_hebrew.py audio.mp3 --ivrit --timestamps

# Translate Hebrew to English (use medium/large, not ivrit)
python transcribe_hebrew.py audio.mp3 --model medium --translate

# View all options
python transcribe_hebrew.py --help
```

## Model Options

### ivrit-ai Models (Recommended for Hebrew)

| Model | Description |
|-------|-------------|
| `ivrit-ai/whisper-large-v3-turbo-ct2` | Fast + accurate (default with `--ivrit`) |
| `ivrit-ai/whisper-large-v3-ct2` | Maximum accuracy |

### Standard Whisper Models

| Model | Params | VRAM | Speed | Hebrew Accuracy |
|-------|--------|------|-------|-----------------|
| tiny | 39M | ~1GB | Fast | Poor |
| base | 74M | ~1GB | Fast | Fair |
| small | 244M | ~2GB | Medium | Good |
| medium | 769M | ~5GB | Slow | Better |
| large | 1550M | ~10GB | Slowest | Best |
| large-v3 | 1550M | ~10GB | Slowest | Best |
| turbo | 809M | ~6GB | Fast | Good |

## Python API

```python
import faster_whisper

# Load the Hebrew-optimized model
model = faster_whisper.WhisperModel("ivrit-ai/whisper-large-v3-turbo-ct2")

# Transcribe with Hebrew settings
segments, info = model.transcribe(
    "audio.mp3",
    language="he",
    beam_size=5,
    vad_filter=True,
)

# Get the text
text = " ".join([seg.text for seg in segments])
print(text)
```

## Installation

The virtual environment is already set up. If you need to reinstall:

```bash
python3 -m venv venv
source venv/bin/activate
pip install openai-whisper faster-whisper
```

### Prerequisites

- **ffmpeg** must be installed:
  ```bash
  # macOS
  brew install ffmpeg
  ```

## Credits

- [OpenAI Whisper](https://github.com/openai/whisper) - Base speech recognition
- [ivrit.ai](https://huggingface.co/ivrit-ai) - Hebrew fine-tuned models
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) - CTranslate2 inference

## References

If using ivrit-ai models, please cite:

```bibtex
@inproceedings{marmor2025building,
  title={Building an Accurate Open-Source Hebrew ASR System through Crowdsourcing},
  author={Marmor, Yanir and Lifshitz, Yair and Snapir, Yoad and Misgav, Kinneret},
  booktitle={Proc. Interspeech 2025},
  pages={723--727},
  year={2025}
}
```
