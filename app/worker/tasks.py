"""Celery task definitions for audio processing."""

import logging
from datetime import datetime
from typing import Any

from celery import Task
from celery.exceptions import MaxRetriesExceededError

from app.config import get_settings
from app.db.models import Enrichment, Recording, RecordingStatus, Transcript
from app.db.session import get_sync_session
from app.processors.analytics import compute_analytics
from app.processors.diarize import assign_speakers_to_transcript, diarize_audio
from app.processors.filename_parser import parse_recording_filename
from app.processors.metadata import extract_metadata
from app.processors.transcribe import segments_to_json, transcribe_audio
from app.services.google_contacts import lookup_caller_name
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


class ProcessingTask(Task):
    """Base task class with error handling and retry logic."""

    autoretry_for = (Exception,)
    retry_backoff = True
    retry_backoff_max = 600  # 10 minutes max backoff
    retry_jitter = True


@celery_app.task(bind=True, base=ProcessingTask, name="process_recording")
def process_recording(self: Task, recording_id: str) -> dict[str, Any]:
    """Process a single recording: metadata, transcription, diarization, analytics.

    Args:
        recording_id: UUID of the recording to process

    Returns:
        Dictionary with processing results

    Raises:
        MaxRetriesExceededError: If max retries exceeded
    """
    logger.info(f"Processing recording: {recording_id}")

    session = get_sync_session()

    try:
        # Get the recording
        recording = session.query(Recording).filter(Recording.id == recording_id).first()

        if not recording:
            logger.error(f"Recording not found: {recording_id}")
            return {"status": "error", "message": "Recording not found"}

        # Update status to processing
        recording.status = RecordingStatus.PROCESSING
        recording.retry_count = self.request.retries
        session.commit()

        file_path = recording.file_path
        logger.info(f"Processing file: {file_path}")

        # Step 0: Parse caller info from filename
        logger.info("Step 0: Parsing caller metadata from filename...")
        try:
            caller_metadata = parse_recording_filename(recording.file_name)

            # Handle phone number
            if caller_metadata.phone_number:
                recording.phone_number = caller_metadata.phone_number
                logger.info(f"Parsed phone number: {caller_metadata.phone_number}")

                # Look up caller name from Google Contacts
                caller_name = lookup_caller_name(caller_metadata.phone_number)
                if caller_name:
                    recording.caller_name = caller_name
                    logger.info(f"Found caller name from contacts: {caller_name}")

            # Handle caller name from filename (e.g., "Call recording Asaf David_...")
            if caller_metadata.caller_name and not recording.caller_name:
                recording.caller_name = caller_metadata.caller_name
                logger.info(f"Parsed caller name from filename: {caller_metadata.caller_name}")

            if caller_metadata.call_datetime:
                recording.call_datetime = caller_metadata.call_datetime
                logger.info(f"Parsed call datetime: {caller_metadata.call_datetime}")

            # Store in metadata_json as well
            if recording.metadata_json is None:
                recording.metadata_json = {}
            recording.metadata_json['caller_info'] = {
                'phone_number': caller_metadata.phone_number,
                'raw_phone': caller_metadata.raw_phone,
                'caller_name': recording.caller_name,
                'caller_name_source': 'filename' if caller_metadata.caller_name else ('contacts' if recording.caller_name else None),
                'call_datetime': caller_metadata.call_datetime.isoformat() if caller_metadata.call_datetime else None,
            }
            session.commit()
        except Exception as e:
            logger.warning(f"Filename parsing failed (continuing): {e}")

        # Step 1: Extract metadata
        logger.info("Step 1: Extracting metadata...")
        try:
            metadata = extract_metadata(file_path)
            recording.duration_sec = metadata.duration_sec
            recording.sample_rate = metadata.sample_rate
            recording.channels = metadata.channels
            recording.codec = metadata.codec
            recording.container = metadata.container
            recording.bit_rate = metadata.bit_rate
            recording.metadata_json = metadata.raw_metadata
            session.commit()
        except Exception as e:
            logger.error(f"Metadata extraction failed: {e}")
            raise

        # Step 2: Transcribe
        logger.info("Step 2: Transcribing audio...")
        try:
            transcript_result = transcribe_audio(file_path)
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            raise

        # Step 3: Diarization (optional)
        segments = transcript_result.segments
        diarization_enabled = settings.diarization_enabled
        speaker_count = 0

        if diarization_enabled:
            logger.info("Step 3: Running diarization...")
            try:
                diarization = diarize_audio(file_path)
                segments = assign_speakers_to_transcript(segments, diarization)
                speaker_count = diarization.speaker_count
            except Exception as e:
                logger.warning(f"Diarization failed (continuing without): {e}")
                diarization_enabled = False

        # Step 4: Compute analytics
        logger.info("Step 4: Computing analytics...")
        try:
            analytics = compute_analytics(
                segments=segments,
                total_duration=metadata.duration_sec,
            )
        except Exception as e:
            logger.error(f"Analytics computation failed: {e}")
            raise

        # Step 5: Store results
        logger.info("Step 5: Storing results...")

        # Create or update transcript
        transcript = (
            session.query(Transcript)
            .filter(Transcript.recording_id == recording.id)
            .first()
        )

        if transcript:
            transcript.text = transcript_result.text
            transcript.language = transcript_result.language
            transcript.language_probability = transcript_result.language_probability
            transcript.segments_json = segments_to_json(segments)
            transcript.model_name = transcript_result.model_name
            transcript.beam_size = transcript_result.beam_size
            transcript.compute_type = transcript_result.compute_type
        else:
            transcript = Transcript(
                recording_id=recording.id,
                model_name=transcript_result.model_name,
                beam_size=transcript_result.beam_size,
                compute_type=transcript_result.compute_type,
                language=transcript_result.language,
                language_probability=transcript_result.language_probability,
                text=transcript_result.text,
                segments_json=segments_to_json(segments),
                transcript_json={
                    "model": transcript_result.model_name,
                    "language_probability": transcript_result.language_probability,
                },
            )
            session.add(transcript)

        # Create or update enrichment
        enrichment = (
            session.query(Enrichment)
            .filter(Enrichment.recording_id == recording.id)
            .first()
        )

        if enrichment:
            enrichment.speaker_count = speaker_count
            enrichment.diarization_enabled = diarization_enabled
            enrichment.total_speech_time = analytics.total_speech_time
            enrichment.total_silence_time = analytics.total_silence_time
            enrichment.talk_time_ratio = analytics.talk_time_ratio
            enrichment.silence_ratio = analytics.silence_ratio
            enrichment.segment_count = analytics.segment_count
            enrichment.avg_segment_length = analytics.avg_segment_length
            enrichment.speaker_turns = analytics.speaker_turns
            enrichment.long_silence_count = analytics.long_silence_count
            enrichment.long_silence_threshold_sec = analytics.long_silence_threshold_sec
            enrichment.analytics_json = analytics.analytics_json
        else:
            enrichment = Enrichment(
                recording_id=recording.id,
                speaker_count=speaker_count,
                diarization_enabled=diarization_enabled,
                total_speech_time=analytics.total_speech_time,
                total_silence_time=analytics.total_silence_time,
                talk_time_ratio=analytics.talk_time_ratio,
                silence_ratio=analytics.silence_ratio,
                segment_count=analytics.segment_count,
                avg_segment_length=analytics.avg_segment_length,
                speaker_turns=analytics.speaker_turns,
                long_silence_count=analytics.long_silence_count,
                long_silence_threshold_sec=analytics.long_silence_threshold_sec,
                analytics_json=analytics.analytics_json,
            )
            session.add(enrichment)

        # Mark as done
        recording.status = RecordingStatus.DONE
        recording.processed_at = datetime.utcnow()
        recording.error_message = None
        session.commit()

        logger.info(f"Processing complete for: {recording_id}")

        return {
            "status": "success",
            "recording_id": str(recording.id),
            "segments": len(segments),
            "speakers": speaker_count,
            "duration_sec": metadata.duration_sec,
        }

    except MaxRetriesExceededError:
        logger.error(f"Max retries exceeded for: {recording_id}")
        recording = session.query(Recording).filter(Recording.id == recording_id).first()
        if recording:
            recording.status = RecordingStatus.FAILED
            recording.error_message = "Max retries exceeded"
            session.commit()
        raise

    except Exception as e:
        logger.error(f"Processing failed for {recording_id}: {e}")

        # Update recording with error
        recording = session.query(Recording).filter(Recording.id == recording_id).first()
        if recording:
            recording.error_message = str(e)
            session.commit()

        # Re-raise for retry
        raise

    finally:
        session.close()

