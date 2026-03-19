# Product Guidelines: Whisper Call Transcription Pipeline

## ✍️ Prose Style & Tone
- **Tone:** Professional, precise, and authoritative. The system should sound like a reliable technical utility.
- **Style:** Use standard technical English (or Hebrew where appropriate) for developer documentation. Avoid jargon where possible, but be precise when discussing technical parameters (e.g., sample rates, WER).
- **Communication:** Documentation should be clear, well-structured, and focused on helping the user achieve their goal quickly.

## 🎨 Branding & Personality
- **Modern & Efficient:** The system is built for speed and high-throughput Hebrew transcription.
- **Transparent & Reliable:** Data integrity is paramount. Every processing step should be logged and auditable.
- **Sophisticated & Analytical:** Focus on the quality of insights—not just "text from audio," but deep understanding of the conversation.

## 🧱 UX & Design Principles
- **API-First Design:** Every feature must be accessible via the REST API before it is added to any UI. The API is the primary product.
- **Visibility of System Status:** Users should always know the state of a recording (e.g., `queued`, `transcribing`, `done`, `failed`). Progress should be trackable via Celery tasks.
- **Robustness & Self-Healing:** The system must gracefully handle network interruptions, database locks, or worker crashes. Automated retries (with exponential backoff) are the default behavior.

## 🚨 Error Handling & Logging
- **Fail-Safe & Silent Recovery:** The pipeline should attempt to recover from transient errors (like temporary API timeouts) silently.
- **Administrative Logging:** Detailed error logs should be available for administrators/developers via Prometheus/Grafana or Flower, but kept out of the high-level user status unless a manual intervention is required.
- **Actionable Insights:** When a task permanently fails (e.g., "corrupt audio file"), the task status should clearly indicate the reason to the user.
