"""Folder watcher service that polls for new audio files and queues them for processing.

Supports optional sync from a source folder (e.g., Google Drive) in batches.
"""

import logging
import shutil
import signal
import sys
import time
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db.models import Recording, RecordingStatus
from app.db.session import SyncSessionLocal
from app.processors.metadata import compute_file_hash

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class FolderWatcher:
    """Watches a folder for new audio files and queues them for processing.
    
    Optionally syncs files from a source folder in batches.
    """

    def __init__(
        self,
        folder: str | Path,
        poll_interval: int = 30,
        stable_seconds: int = 10,
        audio_extensions: tuple[str, ...] = (".m4a", ".mp3", ".wav", ".aac", ".ogg", ".flac"),
        sync_enabled: bool = False,
        source_folder: str | Path | None = None,
        sync_batch_size: int = 20,
    ):
        """
        Initialize the folder watcher.

        Args:
            folder: Path to the folder to watch (and copy files into)
            poll_interval: Seconds between folder scans
            stable_seconds: File must be unmodified for this many seconds
            audio_extensions: Tuple of audio file extensions to process
            sync_enabled: Enable automatic syncing from source folder
            source_folder: Source folder to sync from (e.g., Google Drive)
            sync_batch_size: Number of files to copy per sync batch
        """
        self.folder = Path(folder)
        self.poll_interval = poll_interval
        self.stable_seconds = stable_seconds
        self.audio_extensions = audio_extensions
        self._running = False
        self._last_sizes: dict[str, int] = {}
        
        # Sync settings
        self.sync_enabled = sync_enabled
        self.source_folder = Path(source_folder) if source_folder else None
        self.sync_batch_size = sync_batch_size

    def is_file_ready(self, file_path: Path) -> bool:
        """
        Check if a file is ready for processing.

        A file is ready when:
        1. Its modification time is older than stable_seconds
        2. Its size hasn't changed since the last poll

        Args:
            file_path: Path to the file to check

        Returns:
            True if file is ready for processing
        """
        try:
            stat = file_path.stat()
        except OSError as e:
            logger.warning(f"Cannot stat file {file_path}: {e}")
            return False

        # Check 1: mtime must be old enough
        mtime_age = time.time() - stat.st_mtime
        if mtime_age < self.stable_seconds:
            logger.debug(f"File {file_path.name} too recent (age={mtime_age:.1f}s < {self.stable_seconds}s)")
            return False

        # Check 2: size must be stable
        current_size = stat.st_size
        file_key = str(file_path)
        last_size = self._last_sizes.get(file_key)
        self._last_sizes[file_key] = current_size

        if last_size is None:
            logger.debug(f"File {file_path.name} first observation, size={current_size}")
            return False

        if last_size != current_size:
            logger.debug(f"File {file_path.name} size changed: {last_size} -> {current_size}")
            return False

        return True

    def scan_folder(self) -> list[Path]:
        """
        Scan folder for audio files.

        Returns:
            List of audio file paths
        """
        return [f for f in self.folder.iterdir() if f.is_file() and f.suffix.lower() in self.audio_extensions]

    def scan_source_folder(self) -> list[Path]:
        """
        Scan source folder for audio files.

        Returns:
            List of audio file paths in source folder
        """
        if not self.source_folder or not self.source_folder.exists():
            return []
        
        return [f for f in self.source_folder.iterdir() if f.is_file() and f.suffix.lower() in self.audio_extensions]

    def get_pending_count_in_folder(self) -> int:
        """
        Count files in calls folder that are not yet in the database.
        
        Returns:
            Number of pending files
        """
        audio_files = self.scan_folder()
        if not audio_files:
            return 0

        pending = 0
        session = SyncSessionLocal()
        try:
            # 1. Check by name in batches (faster)
            file_names = [f.name for f in audio_files]
            existing_names = set()
            batch_size = 500

            for i in range(0, len(file_names), batch_size):
                batch = file_names[i:i + batch_size]
                if not batch:
                    continue
                results = session.query(Recording.file_name).filter(
                    Recording.file_name.in_(batch)
                ).all()
                existing_names.update(r[0] for r in results)

            # Identify candidates that passed the name check
            candidates = [f for f in audio_files if f.name not in existing_names]

            if not candidates:
                return 0

            # 2. Check by hash for remaining candidates
            candidate_hashes = {}
            for f in candidates:
                # This might raise an exception if file is unreadable, consistent with original behavior
                h = compute_file_hash(str(f))
                candidate_hashes[f] = h

            hashes_to_check = list(candidate_hashes.values())
            existing_hashes = set()

            if hashes_to_check:
                for i in range(0, len(hashes_to_check), batch_size):
                    batch = hashes_to_check[i:i + batch_size]
                    if not batch:
                        continue
                    results = session.query(Recording.file_hash).filter(
                        Recording.file_hash.in_(batch)
                    ).all()
                    existing_hashes.update(r[0] for r in results)

            for f in candidates:
                if candidate_hashes[f] not in existing_hashes:
                    pending += 1

        finally:
            session.close()
        
        return pending

    def sync_from_source(self) -> int:
        """
        Sync files from source folder to calls folder.
        
        Only copies files that:
        1. Don't already exist in calls folder (by name)
        2. Haven't been processed yet (not in database by hash)
        
        Returns:
            Number of files copied
        """
        if not self.sync_enabled or not self.source_folder:
            return 0
        
        if not self.source_folder.exists():
            logger.warning(f"Source folder does not exist: {self.source_folder}")
            return 0
        
        # Get files in calls folder and source folder
        calls_files = {f.name for f in self.scan_folder()}
        source_files = self.scan_source_folder()
        
        # Get files that are already processed (in database)
        processed_hashes: set[str] = set()
        processed_names: set[str] = set()
        session = SyncSessionLocal()
        try:
            recordings = session.query(Recording.file_hash, Recording.file_name).all()
            processed_hashes = {r.file_hash for r in recordings}
            processed_names = {r.file_name for r in recordings}
        finally:
            session.close()
        
        # Find files to sync (not in calls folder)
        candidates: list[Path] = []
        for source_file in source_files:
            if source_file.name not in calls_files and source_file.name not in processed_names:
                # Check if already processed by hash (in case filename changed but content is same)
                try:
                    file_hash = compute_file_hash(str(source_file))
                    if file_hash not in processed_hashes:
                        candidates.append(source_file)
                except Exception as e:
                    logger.warning(f"Cannot compute hash for {source_file}: {e}")
        
        if not candidates:
            logger.debug("No new files to sync from source")
            return 0
        
        # Sort by modification time (oldest first) and take batch
        candidates.sort(key=lambda f: f.stat().st_mtime)
        batch = candidates[:self.sync_batch_size]
        
        logger.info(f"Syncing {len(batch)} files from source ({len(candidates)} total pending)")
        
        copied = 0
        for source_file in batch:
            dest_path = self.folder / source_file.name
            try:
                shutil.copy2(source_file, dest_path)
                logger.info(f"Copied: {source_file.name}")
                copied += 1
            except Exception as e:
                logger.error(f"Failed to copy {source_file.name}: {e}")
        
        return copied

    def clean_stale_cache(self, current_files: set[str]) -> None:
        """Remove deleted files from size cache."""
        stale_keys = [k for k in self._last_sizes if k not in current_files]
        for key in stale_keys:
            del self._last_sizes[key]
            logger.debug(f"Removed stale cache entry: {key}")

    def process_batch(self, file_paths: list[Path]) -> int:
        """
        Process a batch of files: check if new and queue for transcription.

        Args:
            file_paths: List of file paths to process

        Returns:
            Number of files queued
        """
        if not file_paths:
            return 0

        # 1. Compute hashes for all files
        # Map file_path -> (hash, size)
        file_info: dict[Path, dict] = {}
        for fp in file_paths:
            try:
                h = compute_file_hash(str(fp))
                file_info[fp] = {"hash": h, "size": fp.stat().st_size}
            except Exception as e:
                logger.error(f"Error preparing file {fp}: {e}")
                continue

        if not file_info:
            return 0

        all_hashes = [info["hash"] for info in file_info.values()]
        all_names = [fp.name for fp in file_info.keys()]

        session = SyncSessionLocal()
        queued_count = 0
        try:
            # 2. Check existing recordings
            # Chunk queries to avoid limit
            existing_hashes = set()
            existing_names = set()

            chunk_size = 500
            for i in range(0, len(all_hashes), chunk_size):
                chunk = all_hashes[i:i+chunk_size]
                if chunk:
                    res = session.query(Recording.file_hash).filter(Recording.file_hash.in_(chunk)).all()
                    existing_hashes.update(r.file_hash for r in res)

            for i in range(0, len(all_names), chunk_size):
                chunk = all_names[i:i+chunk_size]
                if chunk:
                    res = session.query(Recording.file_name).filter(Recording.file_name.in_(chunk)).all()
                    existing_names.update(r.file_name for r in res)

            # 3. Filter and Add
            to_add = []
            for fp, info in file_info.items():
                if info["hash"] in existing_hashes:
                    logger.debug(f"File {fp.name} already in database by hash")
                    continue
                if fp.name in existing_names:
                    logger.debug(f"File {fp.name} already in database by name")
                    continue

                recording = Recording(
                    file_path=str(fp.absolute()),
                    file_name=fp.name,
                    file_hash=info["hash"],
                    file_size=info["size"],
                    status=RecordingStatus.QUEUED,
                )
                to_add.append(recording)

                # Update sets for intra-batch deduplication
                existing_hashes.add(info["hash"])
                existing_names.add(fp.name)

            if to_add:
                session.add_all(to_add)
                session.commit()
                # session.refresh() is expensive for list, avoiding unless needed.
                # We don't use the IDs immediately here, just counting.
                # But logging IDs is nice.
                for r in to_add:
                     logger.info(f"Queued new file: {r.file_name} (id={r.id})")
                queued_count = len(to_add)

        except Exception as e:
            logger.error(f"Error processing batch: {e}")
            session.rollback()
            return 0
        finally:
            session.close()

        return queued_count

    def poll_once(self) -> dict[str, Any]:
        """
        Perform a single poll of the folder.
        
        If sync is enabled and queue is low, syncs more files from source.

        Returns:
            Stats dict with counts
        """
        stats = {"scanned": 0, "ready": 0, "queued": 0, "skipped": 0, "synced": 0}

        if not self.folder.exists():
            logger.warning(f"Watch folder does not exist: {self.folder}")
            return stats

        # Sync from source if enabled and queue is low
        if self.sync_enabled:
            pending = self.get_pending_count_in_folder()
            if pending < self.sync_batch_size:
                synced = self.sync_from_source()
                stats["synced"] = synced

        audio_files = self.scan_folder()
        stats["scanned"] = len(audio_files)

        # Clean stale cache entries
        current_files = {str(f) for f in audio_files}
        self.clean_stale_cache(current_files)

        ready_files = []
        for file_path in audio_files:
            if not self.is_file_ready(file_path):
                continue

            stats["ready"] += 1
            ready_files.append(file_path)

        if ready_files:
            queued = self.process_batch(ready_files)
            stats["queued"] = queued
            stats["skipped"] = len(ready_files) - queued

        return stats

    def start(self) -> None:
        """Start the watcher loop."""
        self._running = True
        logger.info(f"Starting folder watcher on {self.folder}")
        logger.info(f"Poll interval: {self.poll_interval}s, Stable threshold: {self.stable_seconds}s")
        
        if self.sync_enabled and self.source_folder:
            logger.info(f"Sync enabled from {self.source_folder} (batch size: {self.sync_batch_size})")
        else:
            logger.info("Sync disabled - processing files in watch folder only")

        while self._running:
            try:
                stats = self.poll_once()
                if stats["queued"] > 0 or stats["ready"] > 0 or stats.get("synced", 0) > 0:
                    logger.info(
                        f"Poll complete: scanned={stats['scanned']}, "
                        f"ready={stats['ready']}, queued={stats['queued']}, "
                        f"skipped={stats['skipped']}, synced={stats.get('synced', 0)}"
                    )
            except Exception as e:
                logger.error(f"Error during poll: {e}", exc_info=True)

            # Sleep in small increments to allow quick shutdown
            for _ in range(self.poll_interval):
                if not self._running:
                    break
                time.sleep(1)

        logger.info("Folder watcher stopped")

    def stop(self) -> None:
        """Stop the watcher loop."""
        logger.info("Stopping folder watcher...")
        self._running = False


def main() -> None:
    """Main entry point for the folder watcher service."""
    settings = get_settings()

    watcher = FolderWatcher(
        folder=settings.calls_dir,
        poll_interval=settings.watcher_poll_interval,
        stable_seconds=settings.watcher_stable_seconds,
        audio_extensions=settings.audio_extensions,
        sync_enabled=settings.sync_enabled,
        source_folder=settings.source_dir if settings.sync_enabled else None,
        sync_batch_size=settings.sync_batch_size,
    )

    # Handle shutdown signals
    def signal_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}")
        watcher.stop()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    try:
        watcher.start()
    except KeyboardInterrupt:
        watcher.stop()

    sys.exit(0)


if __name__ == "__main__":
    main()

