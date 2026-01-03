"""Folder watcher service that polls for new audio files and queues them for processing."""

import logging
import signal
import sys
import time
from pathlib import Path
from typing import Any

from app.config import get_settings
from app.db.models import Recording, RecordingStatus
from app.db.session import SyncSessionLocal
from app.processors.metadata import compute_file_hash
from app.worker.tasks import process_recording

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class FolderWatcher:
    """Watches a folder for new audio files and queues them for processing."""

    def __init__(
        self,
        folder: str | Path,
        poll_interval: int = 30,
        stable_seconds: int = 10,
        audio_extensions: tuple[str, ...] = (".m4a", ".mp3", ".wav", ".aac", ".ogg", ".flac"),
    ):
        """
        Initialize the folder watcher.

        Args:
            folder: Path to the folder to watch
            poll_interval: Seconds between folder scans
            stable_seconds: File must be unmodified for this many seconds
            audio_extensions: Tuple of audio file extensions to process
        """
        self.folder = Path(folder)
        self.poll_interval = poll_interval
        self.stable_seconds = stable_seconds
        self.audio_extensions = audio_extensions
        self._running = False
        self._last_sizes: dict[str, int] = {}

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
        audio_files: list[Path] = []
        for ext in self.audio_extensions:
            audio_files.extend(self.folder.glob(f"*{ext}"))
            audio_files.extend(self.folder.glob(f"*{ext.upper()}"))
        return audio_files

    def clean_stale_cache(self, current_files: set[str]) -> None:
        """Remove deleted files from size cache."""
        stale_keys = [k for k in self._last_sizes if k not in current_files]
        for key in stale_keys:
            del self._last_sizes[key]
            logger.debug(f"Removed stale cache entry: {key}")

    def process_file(self, file_path: Path) -> bool:
        """
        Process a single file: check if new and queue for transcription.

        Args:
            file_path: Path to the audio file

        Returns:
            True if file was queued, False otherwise
        """
        file_hash = compute_file_hash(str(file_path))

        session = SyncSessionLocal()
        try:
            # Check if already in database
            existing = session.query(Recording).filter(
                Recording.file_hash == file_hash
            ).first()

            if existing:
                logger.debug(f"File {file_path.name} already in database (id={existing.id})")
                return False

            # Create new recording
            recording = Recording(
                file_path=str(file_path.absolute()),
                file_name=file_path.name,
                file_hash=file_hash,
                file_size=file_path.stat().st_size,
                status=RecordingStatus.QUEUED,
            )
            session.add(recording)
            session.commit()
            session.refresh(recording)

            # Queue for processing
            process_recording.delay(str(recording.id))
            logger.info(f"Queued new file: {file_path.name} (id={recording.id})")
            return True

        except Exception as e:
            logger.error(f"Error processing file {file_path}: {e}")
            session.rollback()
            return False
        finally:
            session.close()

    def poll_once(self) -> dict[str, Any]:
        """
        Perform a single poll of the folder.

        Returns:
            Stats dict with counts
        """
        stats = {"scanned": 0, "ready": 0, "queued": 0, "skipped": 0}

        if not self.folder.exists():
            logger.warning(f"Watch folder does not exist: {self.folder}")
            return stats

        audio_files = self.scan_folder()
        stats["scanned"] = len(audio_files)

        # Clean stale cache entries
        current_files = {str(f) for f in audio_files}
        self.clean_stale_cache(current_files)

        for file_path in audio_files:
            if not self.is_file_ready(file_path):
                continue

            stats["ready"] += 1

            if self.process_file(file_path):
                stats["queued"] += 1
            else:
                stats["skipped"] += 1

        return stats

    def start(self) -> None:
        """Start the watcher loop."""
        self._running = True
        logger.info(f"Starting folder watcher on {self.folder}")
        logger.info(f"Poll interval: {self.poll_interval}s, Stable threshold: {self.stable_seconds}s")

        while self._running:
            try:
                stats = self.poll_once()
                if stats["queued"] > 0 or stats["ready"] > 0:
                    logger.info(
                        f"Poll complete: scanned={stats['scanned']}, "
                        f"ready={stats['ready']}, queued={stats['queued']}, "
                        f"skipped={stats['skipped']}"
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

