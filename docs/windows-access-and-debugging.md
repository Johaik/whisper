# Windows Server Access and Debugging

How to reach the Windows deployment server and work directly with debugging (logs, database, containers) from your Mac.

## Overview

- **Reach the server:** Ansible over WinRM (no SSH required for Ansible). For monitoring and browser access, use an SSH tunnel from the Mac.
- **App location on Windows:** `C:\app` (configurable via `ansible/group_vars/all.yml` as `win_app_dir`).
- **Run commands on Windows:** Ansible ad-hoc or playbooks; for interactive shell you use SSH (after tunnel or RDP).

---

## 1. Prerequisites

### On your Mac

- **Ansible** and Windows support:
  ```bash
  pip install ansible pywinrm
  ansible-galaxy collection install ansible.windows
  ```
- **Inventory:** Copy `ansible/inventory.ini.example` to `ansible/inventory.ini` and set:
  - `ansible_host` – Windows server IP (e.g. `192.168.50.9`)
  - `ansible_user` – Windows username
  - `ansible_password` – Windows password

### On the Windows server

- WinRM enabled (see [Deployment Guide](deployment.md#1-configure-windows-for-ansible)).
- Docker Desktop with the Whisper stack running under `C:\app`.
- Optional: OpenSSH Server installed (for SSH tunnel and `ssh user@windows-server`).

---

## 2. How You Usually Reach and Access the Windows Server

### Option A: Ansible (primary – no SSH required)

All routine operations (deploy, status, run commands) use Ansible over WinRM.

**Mac-specific:** On macOS, set this before running Ansible to avoid fork-safety errors:

```bash
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
```

**Run from the repo root:**

```bash
cd ansible
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
ansible-playbook status.yaml -i inventory.ini
```

Or use the Makefile (it sets the env for you):

```bash
make status    # Same as above
make deploy    # Full deploy
```

**One-off PowerShell on Windows:**

```bash
cd ansible
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a 'script="docker ps"'
```

Use double quotes for the outer `script=` and escape inner quotes as needed (e.g. `\"` for PowerShell strings that contain `"`). Avoid `{{ }}` in the script string (Ansible treats it as Jinja); for `docker --format` use `{% raw %}...{% endraw %}` in playbooks or a different format in ad-hoc.

### Option B: SSH tunnel (for browser and local tools)

When you need to open the API, Flower, or Grafana in a browser (or run Prometheus on the Mac), use the SSH tunnel so that `localhost` on the Mac maps to the Windows ports.

1. **Start the tunnel** (from repo root or `monitoring/`):
  ```bash
   ./monitoring/tunnel.sh your-username@WINDOWS_IP
  ```
   Example: `./monitoring/tunnel.sh admin@192.168.50.9`
2. **Leave that terminal open.** Then on the Mac:
  - API: [http://localhost:8000](http://localhost:8000)
  - Flower: [http://localhost:5555](http://localhost:5555)
  - Docs: [http://localhost:8000/docs](http://localhost:8000/docs)
3. **Optional – SSH interactive shell:**
  ```bash
   ssh your-username@WINDOWS_IP
  ```
   Then you can run `docker ...`, `cd C:\app`, etc. in PowerShell (or use `powershell` after SSH if your shell is cmd).

### Option C: Remote Desktop (RDP)

For full GUI access, use Microsoft Remote Desktop to the Windows IP. App and data are under `C:\app`. Use this when you need to run PowerShell or Docker Desktop interactively on the server.

---

## 3. Directly Working with Debugging on the Windows Server

Almost all debugging is done by **running commands on the Windows host** via Ansible (or SSH if the tunnel is up). The app runs inside Docker; you don’t edit code on the server—you change code locally, rebuild images, and redeploy.

### 3.1 Viewing logs

**Via Ansible (from Mac):**

```bash
cd ansible
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker logs whisper-worker --tail=50 2>&1\""
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker logs whisper-beat --tail=20 2>&1\""
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker logs whisper-api --tail=30 2>&1\""
```

**If you have an SSH session to Windows:**

```powershell
docker logs whisper-worker --tail=100 -f
docker logs whisper-beat --tail=50
docker logs whisper-api --tail=50
```

### 3.2 Database (PostgreSQL)

**Query the DB via Ansible:**

```bash
cd ansible
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker exec whisper-postgres psql -U whisper -d whisper -c \\\"SELECT status, COUNT(*) FROM recordings GROUP BY status;\\\"\""
```

Use `\"` for the outer script and `\\\"` for the inner SQL so the quote reaches `psql` correctly. For complex SQL, put the query in a playbook or a script on Windows and run that.

**If you have an SSH session:**

```powershell
docker exec -it whisper-postgres psql -U whisper -d whisper
```

Then run SQL (e.g. `\dt`, `SELECT * FROM recordings LIMIT 5;`).

### 3.3 Container and queue status

- **Status playbook (containers, queue, DB summary, Flower):**
  ```bash
  make status
  # or
  cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ansible-playbook status.yaml -i inventory.ini
  ```
- **Deep-dive (DB integrity, processing/stuck, failed recordings):**
  ```bash
  cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ansible-playbook deep_dive.yaml -i inventory.ini
  ```
- **List containers:**
  ```bash
  ansible windows -i inventory.ini -m ansible.windows.win_powershell -a 'script="docker ps -a"'
  ```

### 3.4 Running one-off commands on Windows

**PowerShell one-liner:**

```bash
cd ansible
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a 'script="YOUR_POWERSHELL_COMMAND"'
```

**Examples:**

- Restart worker:
  ```bash
  ansible windows -i inventory.ini -m ansible.windows.win_powershell -a 'script="cd C:\\app; docker compose restart worker"'
  ```
- Reset a recording to queued (replace `RECORDING_ID`):
  ```bash
  ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker exec whisper-postgres psql -U whisper -d whisper -c \\\"UPDATE recordings SET status = 'queued', error_message = NULL WHERE id = 'RECORDING_ID';\\\"\""
  ```

Note: In PowerShell strings passed through Ansible, `C:\app` can be interpreted (e.g. `\a` as bell). Use `C:\\app` or `C:\\\\app` in the script string as needed so the Windows side sees `C:\app`.

### 3.5 “Debugging code” on the server

- **No live code edit on Windows:** The app runs from Docker images (e.g. `ghcr.io/johaik/whisper-worker:latest`). There is no editable repo on the server.
- **Flow:** Change code on your Mac → build images → push → deploy so Windows pulls and runs the new images.
  ```bash
  make push-build   # build and push images
  make deploy       # Ansible: pull, copy compose/env, restart services
  ```
- **Config without rebuild:** Some behavior is controlled by env (e.g. in `C:\app\.env`). Deploy copies `.env` from Ansible; to change env you update the Ansible deploy (e.g. `group_vars` or deploy task that writes `.env`) and re-run deploy, or edit `C:\app\.env` on Windows and restart the relevant containers (e.g. `docker compose restart worker`).

### 3.6 Files and paths on Windows


| Purpose        | Path on Windows             |
| -------------- | --------------------------- |
| App root       | `C:\app`                    |
| Docker Compose | `C:\app\docker-compose.yml` |
| Env            | `C:\app\.env`               |
| Calls (input)  | `C:\app\Calls`              |
| Outputs        | `C:\app\outputs`            |
| Postgres data  | `C:\app\postgres-data`      |
| Redis data     | `C:\app\redis-data`         |
| Copy log       | `C:\app\copied-files.txt`   |


Containers see these as `/data/calls`, `/data/outputs`, etc. (see `docker-compose.yml`).

### 3.7 Debugging when a call (recording) is hanging

A **call** here is a recording being processed (from `Calls/`). If a recording stays in **processing** for a long time, either it’s **slow** (still making progress) or **stuck** (worker died or deadlocked).

**1. Confirm whether it’s stuck vs slow**

- The worker updates `recordings.updated_at` every **heartbeat** (default every 2 minutes) while it’s working.
- If `updated_at` is **recent** (e.g. within the last few minutes), the job is still running (e.g. long transcription or diarization).
- If `updated_at` is **old** (e.g. older than `stuck_processing_threshold_sec`, default 15 minutes), the recording is treated as **stuck** (no heartbeat). The next run of the periodic `enqueue_pending_recordings` beat task will reset it to `queued` or mark `failed` after max retries.

**2. See which recordings are “processing” and how old they are**

Run the deep-dive playbook; it prints “PROCESSING RECORDINGS (stuck check)” with `updated_at` and age:

```bash
cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ansible-playbook deep_dive.yaml -i inventory.ini
```

Or query directly:

```bash
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker exec whisper-postgres psql -U whisper -d whisper -c \\\"SELECT id, file_name, status, duration_sec, updated_at, NOW() - updated_at AS age FROM recordings WHERE status = 'processing';\\\"\""
```

**3. See where the worker is stuck (last log line)**

Worker logs show the pipeline step (Step 0 = filename/caller, Step 1 = metadata, Step 2 = transcribe, Step 3 = diarization, Step 4 = analytics). The **last line** before a long silence is where it’s hanging:

```bash
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker logs whisper-worker --tail=80 2>&1\""
```

**Typical causes of hanging or very long runs:**

| Step | What runs | Why it can hang or run long |
|------|-----------|-----------------------------|
| Step 0 | Filename parsing, **Google Contacts** lookup | Network call to Google can block or be slow. |
| Step 1 | Metadata (ffprobe) | Usually fast; rare I/O or corrupt file. |
| Step 2 | **Transcription** (Whisper) | Long files or CPU-only: can take many minutes. Main culprit for “long” runs. |
| Step 3 | **Diarization** (pyannote) | CPU-heavy; long files (>10 min) are skipped by config, but shorter long files can still be slow. |

**4. Optional: enforce a hard task timeout**

By default there is **no** Celery task time limit (`task_timeout_seconds` is unset). Only “stuck” (no heartbeat) is used. If you want to cap how long a single task can run (e.g. 1 hour), set in `C:\app\.env` (or your deploy env):

```env
TASK_TIMEOUT_SECONDS=3600
```

Redeploy or restart the worker so the new value is picked up. The worker will then apply a soft then hard time limit; the task may be retried up to `task_max_retries`.

**5. Reset a specific recording to retry**

If you’ve identified a recording that’s stuck and want to retry without waiting for the cleanup job:

```bash
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker exec whisper-postgres psql -U whisper -d whisper -c \\\"UPDATE recordings SET status = 'queued', error_message = NULL WHERE id = 'RECORDING_ID';\\\"\""
```

Replace `RECORDING_ID` with the UUID from the “processing” query. The worker will pick it up again (if concurrency allows).

**6. Restart the worker**

If the worker process is unresponsive (e.g. deadlock), restart it:

```bash
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a 'script="cd C:\\app; docker compose restart worker"'
```

After restart, recordings left in `processing` will be detected as stuck (once `updated_at` is older than `stuck_processing_threshold_sec`) and either reset to `queued` by the next run of the periodic `enqueue_pending_recordings` task (every 2 minutes).

---

## 4. Quick reference


| Goal                        | Command / approach                                                                                                                                       |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Check status                | `make status` or `ansible-playbook status.yaml -i inventory.ini`                                                                                         |
| Deep-dive DB + logs         | `ansible-playbook deep_dive.yaml -i inventory.ini`                                                                                                       |
| Worker logs                 | `ansible windows ... -a "script=\"docker logs whisper-worker --tail=50\""`                                                                               |
| Query DB                    | `ansible windows ... -a "script=\"docker exec whisper-postgres psql -U whisper -d whisper -c \\\"SELECT ...\\\"\""`                                      |
| Restart worker              | On Windows: `cd C:\app; docker compose restart worker` (via Ansible or SSH)                                                                              |
| Debug hanging call          | See §3.7: `deep_dive.yaml` for processing/stuck list; worker logs for last step (transcribe/diarization); optional `TASK_TIMEOUT_SECONDS`; reset to queued or restart worker |
| Deploy new code             | `make push-build && make deploy`                                                                                                                         |
| Use API / Flower in browser | Start `./monitoring/tunnel.sh user@WINDOWS_IP`, then open [http://localhost:8000](http://localhost:8000), [http://localhost:5555](http://localhost:5555) |


Always run Ansible from the repo with:

```bash
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
```

when on macOS.