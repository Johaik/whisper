"""Celery task definitions for audio processing."""

import logging
import threading
from datetime import datetime, timedelta
from typing import Any

from billiard.exceptions import SoftTimeLimitExceeded, TimeLimitExceeded
from sqlalchemy.orm import Session
from celery import Task
from celery.exceptions import MaxRetriesExceededError, Retry

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


def _error_message_with_step(session: Session, recording_id: str, base_message: str) -> str:
    """Build error message including current processing step and segment count if in transcribe."""
    rec = session.query(Recording).filter(Recording.id == recording_id).first()
    if not rec:
        return base_message
    step = rec.processing_step or "unknown"
    seg = rec.processing_segments_count
    if seg is not None:
        return f"Step {step} ({seg} segments): {base_message}"
    return f"Step {step}: {base_message}"


class ProcessingTask(Task):
    """Base task class with error handling and retry logic."""

    # Auto-retry on exceptions (but timeout exceptions are handled explicitly and not re-raised)
    autoretry_for = (Exception,)
    retry_kwargs = {"max_retries": settings.task_max_retries}
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
    settings = get_settings()  # Resolve at runtime so tests can patch get_settings

    try:
        # Get the recording
        recording = session.query(Recording).filter(Recording.id == recording_id).first()

        if not recording:
            logger.error(f"Recording not found: {recording_id}")
            return {"status": "error", "message": "Recording not found"}

        # 0) Idempotency: already done (e.g. duplicate task in queue) — skip and return success
        if recording.status == RecordingStatus.DONE:
            logger.info(f"Recording {recording_id} already done, skipping duplicate task")
            return {"status": "success", "recording_id": recording_id, "skipped": True}

        # 1) Refuse to process if already at max retries (e.g. re-queued after failure)
        if (recording.retry_count or 0) >= settings.task_max_retries:
            logger.warning(f"Recording {recording_id} already at max retries ({recording.retry_count}), marking failed")
            recording.status = RecordingStatus.FAILED
            recording.error_message = recording.error_message or "Max retries exceeded"
            session.commit()
            return {"status": "failed", "recording_id": recording_id, "error": "Max retries exceeded"}

        # 2) Ensure PROCESSING and retry_count (enqueue_pending_recordings sets PROCESSING before .delay; no-op if already set)
        recording.status = RecordingStatus.PROCESSING
        recording.retry_count = self.request.retries
        session.commit()

        file_path = recording.file_path
        logger.info(f"Processing file: {file_path}")

        def set_processing_step(step: str) -> None:
            rec = session.query(Recording).filter(Recording.id == recording_id).first()
            if rec:
                rec.processing_step = step
                rec.processing_step_started_at = datetime.utcnow()
                session.commit()

        # Step 0: Parse caller info from filename
        set_processing_step("parse_metadata")
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
        set_processing_step("extract_metadata")
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

        # Heartbeat: update recording.updated_at periodically so "stuck" = no progress, not long runtime
        # Skip when <= 0 (e.g. in tests) to avoid thread/DB contention
        stop_heartbeat = threading.Event()
        heartbeat_interval = max(60, settings.heartbeat_interval_sec) if settings.heartbeat_interval_sec > 0 else 0

        def heartbeat_loop() -> None:
            while True:
                try:
                    hb_session = get_sync_session()
                    try:
                        hb_session.query(Recording).filter(Recording.id == recording_id).update(
                            {Recording.updated_at: datetime.utcnow()},
                            synchronize_session=False,
                        )
                        hb_session.commit()
                    finally:
                        hb_session.close()
                except Exception as e:
                    logger.debug(f"Heartbeat update failed: {e}")
                if stop_heartbeat.wait(heartbeat_interval):
                    break

        heartbeat_thread: threading.Thread | None = None
        if heartbeat_interval > 0:
            heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
            heartbeat_thread.start()
        transcribe_started_at: datetime | None = None
        try:
            # Step 2: Transcribe (with segment progress for API and logs)
            set_processing_step("transcribe")
            recording.processing_segments_count = 0
            session.commit()
            duration_str = f" (duration {metadata.duration_sec / 60:.1f}m)" if metadata.duration_sec else ""
            logger.info("Step 2: Transcribing audio...%s", duration_str)
            logger.info("Transcription progress: 0 segments (started)")
            transcribe_started_at = datetime.utcnow()

            duration_sec = metadata.duration_sec
            estimated_segments = max(1, int((duration_sec or 0) / 30))  # ~2 segments per minute heuristic

            def progress_cb(segments_count: int) -> None:
                rec = session.query(Recording).filter(Recording.id == recording_id).first()
                if rec:
                    rec.processing_segments_count = segments_count
                    if segments_count % 5 == 0 or segments_count == 1:
                        session.commit()
                        pct = min(99, (100 * segments_count) // estimated_segments) if estimated_segments else 0
                        elapsed = (datetime.utcnow() - transcribe_started_at).total_seconds() if transcribe_started_at else 0
                        elapsed_str = f"{int(elapsed // 60)}m" if elapsed >= 60 else f"{int(elapsed)}s"
                        extra = f" (~{pct}% estimated, elapsed {elapsed_str})" if duration_sec else ""
                        logger.info(
                            f"Transcription progress: {segments_count} segment{'s' if segments_count != 1 else ''} (step=transcribe){extra}"
                        )

            try:
                transcript_result = transcribe_audio(file_path, progress_callback=progress_cb)
            except Exception as e:
                logger.error(f"Transcription failed: {e}")
                raise

            # Step 3: Diarization (optional)
            segments = transcript_result.segments
            diarization_enabled = settings.diarization_enabled
            diarization_pending = False
            diarization_skip_reason = None
            speaker_count = 0

            if diarization_enabled:
                # Check if duration exceeds threshold - skip diarization for long recordings
                if metadata.duration_sec and metadata.duration_sec > settings.diarization_max_duration_sec:
                    logger.info(
                        f"Skipping diarization: duration {metadata.duration_sec:.0f}s > "
                        f"{settings.diarization_max_duration_sec}s threshold"
                    )
                    diarization_enabled = False
                    diarization_pending = True
                    diarization_skip_reason = f"duration_exceeded:{metadata.duration_sec:.0f}s"
                else:
                    set_processing_step("diarization")
                    logger.info("Step 3: Running diarization...")
                    try:
                        diarization = diarize_audio(file_path)
                        segments = assign_speakers_to_transcript(segments, diarization)
                        speaker_count = diarization.speaker_count
                    except Exception as e:
                        logger.warning(f"Diarization failed (continuing without): {e}")
                        diarization_enabled = False

            # Step 4: Compute analytics
            set_processing_step("analytics")
            logger.info("Step 4: Computing analytics...")
            try:
                analytics = compute_analytics(
                    segments=segments,
                    total_duration=metadata.duration_sec,
                )
            except Exception as e:
                logger.error(f"Analytics computation failed: {e}")
                raise
        finally:
            stop_heartbeat.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=5)
            # Clear segment and step progress (success or failure)
            rec = session.query(Recording).filter(Recording.id == recording_id).first()
            if rec:
                if rec.processing_segments_count is not None:
                    rec.processing_segments_count = None
                if rec.processing_step is not None or rec.processing_step_started_at is not None:
                    rec.processing_step = None
                    rec.processing_step_started_at = None
                session.commit()

        # Step 5: Store results
        set_processing_step("store_results")
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
            enrichment.diarization_pending = diarization_pending
            enrichment.diarization_skip_reason = diarization_skip_reason
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
                diarization_pending=diarization_pending,
                diarization_skip_reason=diarization_skip_reason,
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

    except (SoftTimeLimitExceeded, TimeLimitExceeded) as e:
        logger.error(f"Timeout exceeded for {recording_id}: {e}")

        # Update recording status based on retry count
        recording = session.query(Recording).filter(Recording.id == recording_id).first()
        if recording:
            retry_count = self.request.retries
            recording.retry_count = retry_count
            recording.error_message = _error_message_with_step(session, recording_id, f"Timeout exceeded: {e}")

            # If we've exceeded max retries, mark as failed
            if retry_count >= settings.task_max_retries:
                logger.error(f"Max retries ({settings.task_max_retries}) exceeded for {recording_id} due to timeout")
                recording.status = RecordingStatus.FAILED
                recording.error_message = _error_message_with_step(
                    session, recording_id, f"Timeout exceeded after {retry_count} retries: {e}"
                )
                session.commit()
                # Don't re-raise - mark as failed and stop
                return {"status": "failed", "recording_id": recording_id, "error": "Timeout exceeded after max retries"}
            else:
                # Reset to queued for retry
                logger.warning(f"Resetting {recording_id} to queued for retry {retry_count + 1}/{settings.task_max_retries}")
                recording.status = RecordingStatus.QUEUED
                session.commit()
                # Re-raise to trigger Celery retry
                raise

    except Retry:
        raise  # Celery retry (e.g. stuck reset to queued) - let it through
    except MaxRetriesExceededError:
        logger.error(f"Max retries exceeded for: {recording_id}")
        recording = session.query(Recording).filter(Recording.id == recording_id).first()
        if recording:
            recording.status = RecordingStatus.FAILED
            # Keep existing error_message (e.g. "Step X (N segments): Timeout exceeded...") so root cause is visible
            recording.error_message = recording.error_message or "Max retries exceeded"
            session.commit()
        raise

    except Exception as e:
        logger.error(f"Processing failed for {recording_id}: {e}")

        # Update recording with error (include step and segments for diagnosis)
        recording = session.query(Recording).filter(Recording.id == recording_id).first()
        if recording:
            retry_count = self.request.retries
            recording.retry_count = retry_count
            recording.error_message = _error_message_with_step(session, recording_id, str(e))
            
            # If we've exceeded max retries, mark as failed
            if retry_count >= settings.task_max_retries:
                logger.error(f"Max retries ({settings.task_max_retries}) exceeded for {recording_id}")
                recording.status = RecordingStatus.FAILED
            else:
                # Reset to queued for retry
                recording.status = RecordingStatus.QUEUED
            session.commit()

        # Re-raise for retry (only if not at max retries)
        if self.request.retries < settings.task_max_retries:
            raise
        else:
            # Max retries reached, don't re-raise
            return {"status": "failed", "recording_id": recording_id, "error": str(e)}

    finally:
        try:
            session.close()
        except Exception as e:
            logger.debug(f"Session close (non-fatal): {e}")
            # Do not re-raise: a successful return must not be turned into a retry
            # by an exception in finally (autoretry_for would then retry the task).


# Max recordings to enqueue per run of enqueue_pending_recordings
ENQUEUE_BATCH_SIZE = 50


@celery_app.task(name="enqueue_pending_recordings")
def enqueue_pending_recordings() -> dict[str, Any]:
    """Single enqueuer: reset stuck PROCESSING to QUEUED (or FAILED), then enqueue QUEUED.

    DB is the source of truth. Only this task calls process_recording.delay().
    Run periodically (e.g. Celery Beat every 1–2 min).
    """
    session = get_sync_session()
    stuck_threshold_sec = settings.stuck_processing_threshold_sec
    cutoff = datetime.utcnow() - timedelta(seconds=stuck_threshold_sec)
    try:
        # Get active tasks from Celery to avoid resetting tasks that are actually running
        active_recording_ids = set()
        try:
            inspect = celery_app.control.inspect()
            active = inspect.active()
            if active:
                for worker_tasks in active.values():
                    for task in worker_tasks:
                        if task.get("name") == "process_recording" and task.get("args"):
                            # recording_id is the first arg
                            try:
                                active_recording_ids.add(task["args"][0])
                            except (IndexError, KeyError):
                                pass
        except Exception as e:
            logger.warning(f"Could not get active tasks during stuck recovery: {e}")

        # 1) Stuck recovery: PROCESSING with updated_at too old -> QUEUED or FAILED
        stuck = (
            session.query(Recording)
            .filter(Recording.status == RecordingStatus.PROCESSING)
            .all()
        )
        failed_count = 0
        queued_count = 0
        now = datetime.utcnow()
        for rec in stuck:
            # If the task is explicitly active in Celery, it's not stuck
            if str(rec.id) in active_recording_ids:
                continue

            updated_naive = rec.updated_at.replace(tzinfo=None) if getattr(rec.updated_at, "tzinfo", None) else rec.updated_at
            if updated_naive is None or updated_naive >= cutoff:
                continue
            age_sec = (now - updated_naive).total_seconds()
            step = rec.processing_step or "?"
            segments = rec.processing_segments_count or 0
            logger.warning(
                "Stuck recording: id=%s file=%s step=%s segments=%s last_update=%s age_sec=%.0f",
                rec.id,
                rec.file_name,
                step,
                segments,
                updated_naive,
                age_sec,
            )
            retry_count = (rec.retry_count or 0) + 1
            rec.retry_count = retry_count
            if retry_count >= settings.task_max_retries:
                rec.status = RecordingStatus.FAILED
                age_min = int(age_sec // 60)
                rec.error_message = (
                    f"Stuck in step {step} ({segments} segments); last update {age_min}m ago (cleanup)"
                )
                failed_count += 1
            else:
                rec.status = RecordingStatus.QUEUED
                rec.error_message = None
                queued_count += 1
        session.commit()
        if failed_count or queued_count:
            logger.info(f"enqueue_pending_recordings: stuck->failed={failed_count}, stuck->queued={queued_count}")

        # 2) Enqueue: QUEUED -> set PROCESSING, then .delay() once per recording
        to_enqueue = (
            session.query(Recording)
            .filter(Recording.status == RecordingStatus.QUEUED)
            .order_by(Recording.updated_at.asc())
            .limit(ENQUEUE_BATCH_SIZE)
            .all()
        )
        enqueued = 0
        for rec in to_enqueue:
            rec.status = RecordingStatus.PROCESSING
            session.commit()
            process_recording.delay(str(rec.id))
            enqueued += 1
        if enqueued:
            logger.info(f"enqueue_pending_recordings: enqueued={enqueued}")

        return {"failed": failed_count, "reset_to_queued": queued_count, "enqueued": enqueued}
    except Exception as e:
        session.rollback()
        logger.exception(f"enqueue_pending_recordings failed: {e}")
        raise
    finally:
        session.close()

