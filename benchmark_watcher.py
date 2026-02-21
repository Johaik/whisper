import time
import os
import uuid
from pathlib import Path
from itertools import islice
from sqlalchemy import create_engine, select, Column, String, Integer, Enum, BigInteger
from sqlalchemy.orm import sessionmaker, DeclarativeBase
import enum

# Define simplified model for benchmark
class Base(DeclarativeBase):
    pass

class RecordingStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"

class Recording(Base):
    __tablename__ = "recordings"

    id = Column(Integer, primary_key=True)
    file_path = Column(String(1024), nullable=False, index=True)
    file_name = Column(String(512), nullable=False)
    file_hash = Column(String(64), nullable=False)
    file_size = Column(BigInteger, nullable=False)
    status = Column(Enum(RecordingStatus), default=RecordingStatus.DISCOVERED)

# Setup simplified DB
engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(bind=engine)
Base.metadata.create_all(engine)

def setup_data(session, num_recordings=1000):
    """Populate DB with some recordings."""
    recordings = []
    for i in range(num_recordings):
        rec = Recording(
            file_path=f"/tmp/audio_{i}.mp3",
            file_name=f"audio_{i}.mp3",
            file_hash=f"hash_{i}",
            file_size=1024,
            status=RecordingStatus.DONE
        )
        recordings.append(rec)
    session.add_all(recordings)
    session.commit()

def compute_file_hash_mock(file_path):
    """Mock hash computation."""
    name = Path(file_path).name
    if name.startswith("audio_"):
        try:
            i = int(name.split("_")[1].split(".")[0])
            return f"hash_{i}"
        except:
            return f"hash_{name}"
    return f"hash_{name}"

def current_implementation(session, file_paths):
    pending = 0
    for file_path in file_paths:
        # First check by name (faster)
        existing_name = session.query(Recording).filter(
            Recording.file_name == file_path.name
        ).first()
        if existing_name:
            continue

        # Then check by hash
        file_hash = compute_file_hash_mock(str(file_path))
        existing_hash = session.query(Recording).filter(
            Recording.file_hash == file_hash
        ).first()
        if not existing_hash:
            pending += 1
    return pending

def optimized_implementation(session, file_paths):
    pending = 0

    file_names = [f.name for f in file_paths]

    # 1. Check by name in batches
    existing_names = set()
    batch_size = 500

    for i in range(0, len(file_names), batch_size):
        batch = file_names[i:i + batch_size]
        results = session.execute(
            select(Recording.file_name).where(Recording.file_name.in_(batch))
        ).scalars().all()
        existing_names.update(results)

    # Identify files that passed the name check
    candidates = [f for f in file_paths if f.name not in existing_names]

    if not candidates:
        return 0

    # 2. Check by hash for remaining candidates
    candidate_hashes = {f: compute_file_hash_mock(str(f)) for f in candidates}
    hashes_to_check = list(candidate_hashes.values())

    existing_hashes = set()
    for i in range(0, len(hashes_to_check), batch_size):
        batch = hashes_to_check[i:i + batch_size]
        results = session.execute(
            select(Recording.file_hash).where(Recording.file_hash.in_(batch))
        ).scalars().all()
        existing_hashes.update(results)

    for f in candidates:
        if candidate_hashes[f] not in existing_hashes:
            pending += 1

    return pending

def run_benchmark():
    session = SessionLocal()
    setup_data(session)

    # Create dummy file paths
    # 500 existing files, 500 new files
    files = []
    for i in range(500): # Existing
        files.append(Path(f"/tmp/audio_{i}.mp3"))
    for i in range(500): # New
        files.append(Path(f"/tmp/new_audio_{i}.mp3"))

    print(f"Benchmarking with {len(files)} files...")

    start_time = time.time()
    pending_count_current = current_implementation(session, files)
    end_time = time.time()
    current_duration = end_time - start_time
    print(f"Current implementation: {current_duration:.4f}s (Pending: {pending_count_current})")

    start_time = time.time()
    pending_count_optimized = optimized_implementation(session, files)
    end_time = time.time()
    optimized_duration = end_time - start_time
    print(f"Optimized implementation: {optimized_duration:.4f}s (Pending: {pending_count_optimized})")

    assert pending_count_current == pending_count_optimized, "Mismatch in pending count!"

    improvement = (current_duration - optimized_duration) / current_duration * 100
    print(f"Improvement: {improvement:.2f}%")

if __name__ == "__main__":
    run_benchmark()
