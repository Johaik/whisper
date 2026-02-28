"""FastAPI route definitions."""

import logging
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

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

    # Check storage
    try:
        calls_dir = Path(settings.calls_dir).resolve()
        if calls_dir.exists() and calls_dir.is_dir():
            # Check write permission
            test_file = calls_dir / f".health_check_{uuid4()}"
            try:
                test_file.touch()
                test_file.unlink()
                storage_status = "ok"
            except Exception:
                storage_status = "read_only"
        else:
            storage_status = "error"
    except Exception as e:
        logger.error(f"Storage health check failed: {e}")
        storage_status = "error"

    overall = "ok" if db_status == "ok" and redis_status == "ok" and storage_status == "ok" else "degraded"

    return HealthResponse(
        status=overall,
        version=__version__,
        database=db_status,
        redis=redis_status,
        storage=storage_status,
        workers=workers,
    )


@router.get("/queue/status", response_model=QueueStatusResponse)
async def queue_status(
    session: AsyncSessionDep,
    _: AuthDep,
    threshold: int = Query(default=20, description="Queue threshold"),
) -> QueueStatusResponse:
    """Get queue status for batch sync decisions.
    
    Used by the batch-copy script to determine if more files should be copied.
    Authentication required.
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
    folder_path = Path(folder).resolve()

    # Security check: Ensure folder is within allowed directories
    allowed_paths = [Path(settings.calls_dir).resolve()]
    if settings.source_dir:
        allowed_paths.append(Path(settings.source_dir).resolve())

    is_allowed = any(folder_path.is_relative_to(allowed) for allowed in allowed_paths)

    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: Folder must be within allowed directories",
        )

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

    # Find all audio files recursively
    audio_files: list[Path] = [
        f for f in folder_path.rglob("*")
        if f.is_file() and f.suffix.lower() in settings.audio_extensions
    ]

    logger.info(f"Found {len(audio_files)} audio files")

    file_data_list = []

    # 1. First pass: compute hashes and gather metadata
    for audio_file in audio_files:
        try:
            file_path = str(audio_file.absolute())
            file_name = audio_file.name
            file_size = audio_file.stat().st_size
            file_hash = compute_file_hash(file_path)

            file_data_list.append({
                "path": file_path,
                "name": file_name,
                "size": file_size,
                "hash": file_hash,
                "file": audio_file # Keep reference for error reporting
            })
        except Exception as e:
            logger.error(f"Error accessing file {audio_file}: {e}")
            errors.append(f"{audio_file.name}: {str(e)}")

    if not file_data_list:
        logger.info("No valid files to process.")
        return IngestResponse(
            discovered=0,
            queued=0,
            skipped=0,
            errors=errors,
        )

    # 2. Bulk fetch existing recordings
    # Split into chunks to avoid potential query limits if many files
    all_hashes = [f["hash"] for f in file_data_list]
    existing_map: dict[str, Recording] = {}
    chunk_size = 500

    try:
        for i in range(0, len(all_hashes), chunk_size):
            chunk = all_hashes[i : i + chunk_size]
            result = await session.execute(
                select(Recording).where(Recording.file_hash.in_(chunk))
            )
            for rec in result.scalars().all():
                existing_map[rec.file_hash] = rec
    except Exception as e:
        logger.error(f"Error querying existing recordings: {e}")
        # Fail the whole batch if we can't check existence reliably
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error during ingest: {str(e)}",
        )

    # 3. Process files
    processed_hashes = set()

    for f_data in file_data_list:
        file_hash = f_data["hash"]

        if file_hash in processed_hashes:
            skipped += 1
            continue

        existing = existing_map.get(file_hash)

        try:
            if existing:
                if request.force_reprocess or existing.status == RecordingStatus.FAILED:
                    # Reset for reprocessing
                    existing.status = RecordingStatus.QUEUED
                    existing.error_message = None
                    existing.retry_count = 0
                    session.add(existing)  # Ensure it's in session
                    queued += 1
                else:
                    skipped += 1
            else:
                # Create new recording
                recording = Recording(
                    file_path=f_data["path"],
                    file_name=f_data["name"],
                    file_hash=file_hash,
                    file_size=f_data["size"],
                    status=RecordingStatus.QUEUED,
                )
                session.add(recording)

                discovered += 1
                queued += 1

            processed_hashes.add(file_hash)

        except Exception as e:
            # Should not happen for in-memory logic, but just in case
            logger.error(f"Error preparing file {f_data['name']}: {e}")
            errors.append(f"{f_data['name']}: {str(e)}")

    # 4. Commit all changes
    try:
        if queued > 0:
            await session.commit()
    except Exception as e:
        logger.error(f"Database commit failed: {e}")
        # If commit fails, we don't know which one failed easily.
        # Since we pre-checked for existence, duplicates are unlikely.
        errors.append(f"Batch commit failed: {str(e)}")
        # Reset counters as we failed to persist
        discovered = 0
        queued = 0
        skipped = 0

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

