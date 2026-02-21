"""FastAPI route definitions."""

import logging
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app import __version__
from app.api.schemas import (
    EnrichmentDetail,
    HealthResponse,
    PingResponse,
    IngestRequest,
    IngestResponse,
    QueueStatusResponse,
    RecordingDetail,
    RecordingList,
    RecordingListItem,
    ReprocessResponse,
    TranscriptDetail,
    TranscriptSegment,
)
from app.auth import verify_token
from app.config import Settings, get_settings
from app.db.models import Enrichment, Recording, RecordingStatus, Transcript
from app.db.session import get_async_session
from app.processors.metadata import compute_file_hash

logger = logging.getLogger(__name__)

router = APIRouter()


# Dependency shortcuts
AsyncSessionDep = Annotated[AsyncSession, Depends(get_async_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
AuthDep = Annotated[str, Depends(verify_token)]


@router.get("/ping", response_model=PingResponse)
async def ping() -> PingResponse:
    """Simple ping endpoint."""
    return PingResponse(status="pong")


@router.get("/health", response_model=HealthResponse)
async def health_check(
    session: AsyncSessionDep,
    settings: SettingsDep,
) -> HealthResponse:
    """Check service health."""
    # Check database
    try:
        await session.execute(select(1))
        db_status = "ok"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "error"

    # Check Redis (via Celery)
    try:
        from app.worker.celery_app import celery_app

        inspect = celery_app.control.inspect()
        active = inspect.active()
        workers = len(active) if active else 0
        redis_status = "ok"
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        redis_status = "error"
        workers = None

    overall = "ok" if db_status == "ok" and redis_status == "ok" else "degraded"

    return HealthResponse(
        status=overall,
        version=__version__,
        database=db_status,
        redis=redis_status,
        workers=workers,
    )


@router.get("/queue/status", response_model=QueueStatusResponse)
async def queue_status(
    session: AsyncSessionDep,
    threshold: int = Query(default=20, description="Queue threshold"),
) -> QueueStatusResponse:
    """Get queue status for batch sync decisions.
    
    Used by the batch-copy script to determine if more files should be copied.
    No authentication required for simpler integration.
    """
    # Count recordings by status
    queued_count = await session.scalar(
        select(func.count(Recording.id)).where(
            Recording.status == RecordingStatus.QUEUED
        )
    ) or 0
    
    processing_count = await session.scalar(
        select(func.count(Recording.id)).where(
            Recording.status == RecordingStatus.PROCESSING
        )
    ) or 0
    
    # Check active Celery tasks
    active_tasks = 0
    active_recording_ids = set()
    try:
        from app.worker.celery_app import celery_app
        inspect = celery_app.control.inspect()
        active = inspect.active()
        if active:
            for worker_tasks in active.values():
                for task in worker_tasks:
                    active_tasks += 1
                    if task.get("name") == "process_recording" and task.get("args"):
                        try:
                            active_recording_ids.add(str(task["args"][0]))
                        except (IndexError, KeyError):
                            pass
    except Exception as e:
        logger.warning(f"Could not get Celery status: {e}")
    
    # Adjust processing_count to reflect ACTUAL active tasks
    # If DB says 'processing' but Celery doesn't know about it, it's effectively 'stuck' or 'queued'
    # For reporting, we'll show what's actually moving.
    real_processing_count = len(active_recording_ids)
    
    total_pending = queued_count + processing_count
    can_accept = total_pending < threshold
    
    return QueueStatusResponse(
        queued=queued_count,
        processing=real_processing_count,
        active_tasks=active_tasks,
        can_accept_more=can_accept,
        threshold=threshold,
    )


@router.post("/ingest", response_model=IngestResponse)
async def ingest_folder(
    request: IngestRequest,
    session: AsyncSessionDep,
    settings: SettingsDep,
    _: AuthDep,
) -> IngestResponse:
    """Scan a folder for audio files and queue them for processing."""
    folder = request.folder or settings.calls_dir
    folder_path = Path(folder)

    if not folder_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Folder not found: {folder}",
        )

    if not folder_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path is not a directory: {folder}",
        )

    logger.info(f"Scanning folder for audio files: {folder}")

    discovered = 0
    queued = 0
    skipped = 0
    errors: list[str] = []

    # Find all audio files
    audio_files: list[Path] = []
    for ext in settings.audio_extensions:
        audio_files.extend(folder_path.glob(f"*{ext}"))
        audio_files.extend(folder_path.glob(f"*{ext.upper()}"))

    logger.info(f"Found {len(audio_files)} audio files")

    for audio_file in audio_files:
        try:
            file_path = str(audio_file.absolute())
            file_name = audio_file.name
            file_size = audio_file.stat().st_size
            file_hash = compute_file_hash(file_path)

            # Check if already exists
            result = await session.execute(
                select(Recording).where(Recording.file_hash == file_hash)
            )
            existing = result.scalar_one_or_none()

            if existing:
                if request.force_reprocess or existing.status == RecordingStatus.FAILED:
                    # Reset for reprocessing
                    existing.status = RecordingStatus.QUEUED
                    existing.error_message = None
                    existing.retry_count = 0
                    await session.commit()
                    queued += 1
                else:
                    skipped += 1
            else:
                # Create new recording
                recording = Recording(
                    file_path=file_path,
                    file_name=file_name,
                    file_hash=file_hash,
                    file_size=file_size,
                    status=RecordingStatus.QUEUED,
                )
                session.add(recording)
                await session.commit()
                await session.refresh(recording)

                discovered += 1
                queued += 1

        except Exception as e:
            logger.error(f"Error processing file {audio_file}: {e}")
            errors.append(f"{audio_file.name}: {str(e)}")

    logger.info(
        f"Ingest complete: discovered={discovered}, queued={queued}, skipped={skipped}"
    )

    return IngestResponse(
        discovered=discovered,
        queued=queued,
        skipped=skipped,
        errors=errors,
    )


@router.get("/recordings", response_model=RecordingList)
async def list_recordings(
    session: AsyncSessionDep,
    _: AuthDep,
    status_filter: RecordingStatus | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> RecordingList:
    """List recordings with optional status filter and pagination."""
    # Build query
    query = select(Recording)

    if status_filter:
        query = query.where(Recording.status == status_filter)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(Recording.created_at.desc()).offset(offset).limit(page_size)

    result = await session.execute(query)
    recordings = result.scalars().all()

    items = [RecordingListItem.model_validate(r) for r in recordings]

    return RecordingList(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_more=(offset + len(items)) < total,
    )


@router.get("/recordings/{recording_id}", response_model=RecordingDetail)
async def get_recording(
    recording_id: UUID,
    session: AsyncSessionDep,
    _: AuthDep,
) -> RecordingDetail:
    """Get full details for a recording including transcript and enrichment."""
    query = (
        select(Recording)
        .options(selectinload(Recording.transcript), selectinload(Recording.enrichment))
        .where(Recording.id == recording_id)
    )

    result = await session.execute(query)
    recording = result.scalar_one_or_none()

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording not found: {recording_id}",
        )

    # Build response
    response = RecordingDetail.model_validate(recording)

    # Add transcript with parsed segments
    if recording.transcript:
        segments = []
        if recording.transcript.segments_json:
            segments = [
                TranscriptSegment(**seg) for seg in recording.transcript.segments_json
            ]

        response.transcript = TranscriptDetail(
            id=recording.transcript.id,
            model_name=recording.transcript.model_name,
            beam_size=recording.transcript.beam_size,
            compute_type=recording.transcript.compute_type,
            language=recording.transcript.language,
            language_probability=recording.transcript.language_probability,
            text=recording.transcript.text,
            segments=segments,
            created_at=recording.transcript.created_at,
        )

    # Add enrichment
    if recording.enrichment:
        response.enrichment = EnrichmentDetail.model_validate(recording.enrichment)

    return response


@router.post("/recordings/{recording_id}/reprocess", response_model=ReprocessResponse)
async def reprocess_recording(
    recording_id: UUID,
    session: AsyncSessionDep,
    _: AuthDep,
) -> ReprocessResponse:
    """Queue a recording for reprocessing."""
    result = await session.execute(
        select(Recording).where(Recording.id == recording_id)
    )
    recording = result.scalar_one_or_none()

    if not recording:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Recording not found: {recording_id}",
        )

    # Reset status
    recording.status = RecordingStatus.QUEUED
    recording.error_message = None
    recording.retry_count = 0
    await session.commit()

    # Periodic enqueue_pending_recordings will enqueue this (status=QUEUED)
    logger.info(f"Reprocessing queued for: {recording_id}")

    return ReprocessResponse(
        recording_id=recording.id,
        status="queued",
        message="Recording queued for reprocessing",
    )

