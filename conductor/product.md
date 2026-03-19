# Product Definition: Whisper Call Transcription Pipeline

## 🏁 Initial Concept
A production-ready call recording transcription system that automatically processes audio files, transcribes Hebrew speech, identifies speakers, and provides rich analytics—all accessible via a REST API.

## 🎯 Target Users
- **Call Centers & CRM Integration:** High-volume Hebrew call analytics and speaker tracking.
- **Researchers & Journalists:** Ideal for processing interviews and focus groups with multiple speakers.
- **SaaS Developers:** A reliable API for adding Hebrew STT to third-party applications.

## 🌟 Core Value Proposition
- **Hebrew-First Accuracy:** Superior Hebrew speech-to-text accuracy using `ivrit-ai` models fine-tuned on 295+ hours of speech.
- **Advanced Diarization & Analytics:** High-precision speaker identification and talk-time analytics using `pyannote.audio`.
- **End-to-End Automation:** A fully automated pipeline—from file discovery and metadata parsing to transcription and storage.

## 🚀 Key Features
- **Hebrew Transcription:** State-of-the-art Hebrew transcription with VAD filtering.
- **Speaker Diarization:** Multi-speaker identification with overlap detection.
- **Call Analytics:** Detailed metrics including talk time, silence ratio, and speaker turns.
- **Semantic Intelligence:** Semantic similarity search using vector embeddings (PGVector) to find relevant call segments across the database.
- **CQRS Analytics:** High-performance behavioral analytics (WPM, turn velocity, overlap) driven by a Command-Query separation pattern for near-instant reporting.
- **Auto-Discovery:** Independent watcher service for seamless file ingestion.

## 📈 Success Metrics
- **Hebrew Accuracy:** Achieve a Word Error Rate (WER) of less than 10%.
- **Diarization Precision:** Maintain high speaker separation accuracy even in complex recordings.
- **Deep Insights:** Providing advanced call analytics that accurately capture emotions and qualitative data from calls.
