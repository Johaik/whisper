---
name: windows-access-debug
description: Access and debug the Whisper Windows deployment from a Mac. Covers Ansible over WinRM, SSH tunnel for API/Flower, viewing logs and DB, diagnosing stuck recordings, and reset/restart. Use when the user asks how to access Windows, debug the Windows machine, run commands on Windows, check worker logs, query the database on Windows, or troubleshoot stuck/hanging recordings.
---

# Windows Access and Debugging

How to reach the Windows deployment and debug it from your Mac. App runs in Docker at `C:\app`; you run commands via Ansible or SSH.

## Always: macOS Ansible

On macOS, set this before any Ansible command (playbook or ad-hoc) to avoid "worker in dead state":

```bash
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
```

Or use the wrapper: `cd ansible && ./run-playbook.sh <playbook> -i inventory.ini`

---

## 1. Accessing the Windows Server

| Method | Use case |
|--------|----------|
| **Ansible (WinRM)** | Deploy, status, run one-off commands. No SSH needed. |
| **SSH tunnel** | Open API/Flower/Grafana in browser on Mac (localhost → Windows ports). |
| **RDP** | Full GUI on the Windows box. |

**Ansible one-liner (from repo root):**

```bash
cd ansible
export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a 'script="docker ps -a"'
```

**SSH tunnel (for browser access):**

```bash
./monitoring/tunnel.sh your-username@WINDOWS_IP
# Then: http://localhost:8000 (API), http://localhost:5555 (Flower)
```

**Makefile (sets OBJC for you):** `make status`, `make deploy`

---

## 2. Debugging: Logs and Database

**Worker / Beat / API logs (PowerShell via Ansible):**

```bash
cd ansible && export OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker logs whisper-worker --tail=50 2>&1\""
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker logs whisper-beat --tail=20 2>&1\""
```

**Database query (escape quotes: outer script=\"...\", inner SQL \\\"...\\\"):**

```bash
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker exec whisper-postgres psql -U whisper -d whisper -c \\\"SELECT status, COUNT(*) FROM recordings GROUP BY status;\\\"\""
```

**Deep-dive (DB integrity, processing/stuck, failed list):**

```bash
cd ansible && OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES ansible-playbook deep_dive.yaml -i inventory.ini
```

---

## 3. Stuck or Hanging Recordings

- **Stuck** = `status = processing` and `updated_at` older than ~15 min (no heartbeat). Periodic task will reset to queued or failed.
- **Slow** = `updated_at` recent; job still running (e.g. long transcribe/diarization).

**See processing rows and age:**

```bash
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker exec whisper-postgres psql -U whisper -d whisper -c \\\"SELECT id, file_name, status, updated_at, NOW() - updated_at AS age FROM recordings WHERE status = 'processing';\\\"\""
```

**Reset one recording to retry (replace RECORDING_ID):**

```bash
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker exec whisper-postgres psql -U whisper -d whisper -c \\\"UPDATE recordings SET status = 'queued', error_message = NULL WHERE id = 'RECORDING_ID';\\\"\""
```

**Restart worker:**

```bash
ansible windows -i inventory.ini -m ansible.windows.win_powershell -a 'script="cd C:\\app; docker compose restart worker"'
```

---

## 4. Paths and Containers

| On Windows | Purpose |
|------------|--------|
| `C:\app` | App root, docker-compose, .env |
| `C:\app\Calls` | Input recordings |
| `C:\app\outputs` | Outputs |

Containers: `whisper-worker`, `whisper-beat`, `whisper-api`, `whisper-postgres`, `whisper-redis`, `whisper-flower`. Use `docker logs <name>`, `docker exec <name> ...` as above.

---

## 5. Quick Reference

| Goal | Command |
|------|---------|
| Status (containers, queue, DB) | `make status` or `ansible-playbook status.yaml -i inventory.ini` |
| Deep-dive (stuck/failed, logs) | `ansible-playbook deep_dive.yaml -i inventory.ini` |
| Worker logs | `ansible windows -i inventory.ini -m ansible.windows.win_powershell -a "script=\"docker logs whisper-worker --tail=50\""` |
| Restart worker | `ansible windows ... -a 'script="cd C:\\app; docker compose restart worker"'` |
| Purge Celery queue + result backend | `ansible-playbook purge_celery_queue.yaml -i inventory.ini` |
| Deploy new code | `make push-build && make deploy` |

Always run from `ansible/` (or repo root with `cd ansible`), use `-i inventory.ini`, and on macOS set `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` for Ansible.

---

## Full Documentation

For prerequisites, WinRM/SSH setup, and detailed troubleshooting, see `docs/windows-access-and-debugging.md` in the repo.
