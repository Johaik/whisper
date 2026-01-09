# Google Drive Integration

This guide explains how to process audio files from Google Drive on your Windows machine.

## Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    FILE PROCESSING FLOW                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Google Drive (Source)                                           │
│  H:\My Drive\calls                                               │
│  └── 3,784 audio files                                           │
│           │                                                      │
│           │  batch-copy.ps1                                      │
│           │  (copies 50 files at a time)                         │
│           ▼                                                      │
│  Processing Folder                                               │
│  C:\app\Calls                                                    │
│  └── 50 files at a time                                          │
│           │                                                      │
│           │  Watcher detects new files                           │
│           ▼                                                      │
│  Celery Worker                                                   │
│  └── Transcribes one file at a time                              │
│           │                                                      │
│           ▼                                                      │
│  Database + Output Files                                         │
│  └── Results stored permanently                                  │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Why Batch Processing?

With 4,000+ files:
- Queuing all at once would overwhelm the system
- Batch processing gives you control
- You can pause/resume anytime
- Progress is tracked

## Setup

### 1. Google Drive Desktop

Ensure Google Drive is installed and synced:
- Drive path: `H:\My Drive\calls` (or similar)
- Enable "Available offline" for the calls folder

### 2. Deployment Creates Script

When you run `make deploy`, a batch script is created:
```
C:\app\batch-copy.ps1
```

## Using the Batch Script

### Run Manually (PowerShell)

```powershell
# Navigate to app directory
cd C:\app

# Copy next 50 files (default)
.\batch-copy.ps1

# Copy custom batch size
.\batch-copy.ps1 -BatchSize 100

# Specify custom source folder
.\batch-copy.ps1 -Source "D:\My Drive\recordings"
```

### Script Output

```
=== Batch Copy Script ===
Source: H:\My Drive\calls
Destination: C:\app\Calls
Batch Size: 50

Total files in source: 3784
Already processed: 500
Pending: 3284

Copying 50 files...
  [1/50] Call recording John_240115_103045.m4a
  [2/50] Call recording Jane_240115_110230.m4a
  ...
  [50/50] Call recording Bob_240115_143022.m4a

Batch complete: 50 files copied
Remaining: 3234 files

Monitor processing with: docker logs -f whisper-worker
```

### Track Progress

The script tracks copied files in:
```
C:\app\processed-files.txt
```

View progress:
```powershell
# Count processed files
(Get-Content C:\app\processed-files.txt).Count

# See last 10 processed
Get-Content C:\app\processed-files.txt | Select-Object -Last 10
```

## Automation (Optional)

### Schedule with Task Scheduler

Create a scheduled task to run automatically:

1. Open Task Scheduler
2. Create Basic Task
3. Set trigger (e.g., every hour)
4. Action: Start a program
   - Program: `powershell.exe`
   - Arguments: `-File C:\app\batch-copy.ps1 -BatchSize 50`

### Simple Loop Script

Create `C:\app\process-all.ps1`:

```powershell
# Process all files with delay between batches
$batchSize = 50
$delayMinutes = 5

while ($true) {
    # Run batch copy
    & C:\app\batch-copy.ps1 -BatchSize $batchSize
    
    # Check if done
    $pending = (Get-ChildItem "H:\My Drive\calls" -File).Count - 
               (Get-Content "C:\app\processed-files.txt" -ErrorAction SilentlyContinue).Count
    
    if ($pending -le 0) {
        Write-Host "All files processed!"
        break
    }
    
    Write-Host "Waiting $delayMinutes minutes before next batch..."
    Write-Host "Pending: $pending files"
    Start-Sleep -Seconds ($delayMinutes * 60)
}
```

Run in background:
```powershell
Start-Job -FilePath C:\app\process-all.ps1
```

## Monitoring

### Worker Status

```powershell
# Follow worker logs
docker logs -f whisper-worker

# Check current status
docker logs --tail 20 whisper-worker
```

### Queue Status

```powershell
# See pending tasks
docker exec whisper-redis redis-cli LLEN celery
```

### Database Records

Via API (from Windows):
```powershell
$token = "dev-token-change-me"
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/recordings?page_size=5" `
  -Headers @{ Authorization = "Bearer $token" }
```

## Processing Speed

Estimated times (CPU only):

| Batch Size | Audio Length (avg) | Processing Time |
|------------|-------------------|-----------------|
| 50 files | 1 min each | ~25 minutes |
| 50 files | 5 min each | ~2 hours |
| 50 files | 10 min each | ~4 hours |

**Tip:** Process overnight for large batches.

## Troubleshooting

### Script Not Found

```powershell
# Regenerate by redeploying
cd /path/to/whisper
make deploy
```

### Google Drive Not Accessible

```powershell
# Check drive letter
Get-PSDrive -PSProvider FileSystem

# Update script source path if needed
.\batch-copy.ps1 -Source "G:\My Drive\calls"
```

### Files Not Processing

```powershell
# Check watcher logs
docker logs whisper-watcher

# Check worker logs
docker logs whisper-worker

# Restart services
docker compose restart watcher worker
```

### Reset Progress

To reprocess all files:

```powershell
# Clear tracking file
Remove-Item C:\app\processed-files.txt

# Clear existing database entries (optional)
docker compose down
Remove-Item -Recurse C:\app\postgres-data
docker compose up -d
```

## Safety Features

1. **Original files unchanged** - Files are copied, never moved
2. **Progress tracking** - Script remembers what's been copied
3. **Deduplication** - Watcher uses file hash to avoid reprocessing
4. **Controlled pace** - You decide batch size and timing
5. **Pausable** - Stop anytime, resume later

## Example Workflow

```powershell
# Day 1: Start processing
cd C:\app
.\batch-copy.ps1 -BatchSize 100  # Copy first 100 files

# Monitor for a while
docker logs -f whisper-worker

# Check results
Invoke-RestMethod http://localhost:8000/api/v1/recordings | Select total

# Day 2: Continue
.\batch-copy.ps1 -BatchSize 200  # Copy next 200 files

# Weekend: Process the rest
.\process-all.ps1  # Automated batching
```
