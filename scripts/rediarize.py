#!/usr/bin/env python3
"""
Script to trigger re-diarization of recordings.
Can process all recordings where diarization was skipped, or a specific recording ID.
"""

import argparse
import sys
import uuid
from typing import List, Optional

# Add the parent directory to sys.path to import app
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.worker.tasks import enqueue_rediarization_tasks, rediarize_recording

def main():
    parser = argparse.ArgumentParser(description="Trigger re-diarization of recordings.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all-pending", action="store_true", help="Process all recordings where diarization is pending")
    group.add_argument("--id", type=str, help="Process a specific recording ID")
    
    parser.add_argument("--force", action="store_true", help="Force re-diarization even if status is not DONE or diarization is not pending")
    parser.add_argument("--sync", action="store_true", help="Run synchronously instead of enqueuing (for specific ID only)")

    args = parser.parse_args()

    if args.all_pending:
        print("Enqueuing all pending recordings for re-diarization...")
        result = enqueue_rediarization_tasks.delay(force=args.force)
        print(f"Task enqueued: {result.id}")
        print("Check worker logs for progress.")
    
    elif args.id:
        try:
            # Validate UUID
            uuid.UUID(args.id)
        except ValueError:
            print(f"Error: Invalid UUID format: {args.id}")
            sys.exit(1)
            
        if args.sync:
            print(f"Running re-diarization for {args.id} synchronously...")
            result = rediarize_recording(args.id, force=args.force)
            print(f"Result: {result}")
        else:
            print(f"Enqueuing re-diarization for {args.id}...")
            task = rediarize_recording.delay(args.id, force=args.force)
            print(f"Task enqueued: {task.id}")
            print("Check worker logs for progress.")

if __name__ == "__main__":
    main()
