# Monitoring

Remote monitoring for the Whisper Transcription Pipeline. The monitoring stack runs on your Mac and connects to the Windows server via SSH tunnel, ensuring zero performance impact on transcription workloads.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            WINDOWS SERVER (Production)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌───────────────────────────────────────────────────────────────────┐     │
│   │                     DOCKER CONTAINERS                              │     │
│   │                                                                    │     │
│   │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐          │     │
│   │  │   API    │  │  Worker  │  │ Postgres │  │  Redis   │          │     │
│   │  │  :8000   │  │          │  │  :5432   │  │  :6379   │          │     │
│   │  └────┬─────┘  └──────────┘  └────┬─────┘  └────┬─────┘          │     │
│   │       │                           │             │                 │     │
│   │       │ /metrics                  │             │                 │     │
│   │       ▼                           ▼             ▼                 │     │
│   │  ┌──────────┐              ┌──────────┐  ┌──────────┐            │     │
│   │  │  Flower  │              │ Postgres │  │  Redis   │            │     │
│   │  │  :5555   │              │ Exporter │  │ Exporter │            │     │
│   │  │ /metrics │              │  :9187   │  │  :9121   │            │     │
│   │  └──────────┘              └──────────┘  └──────────┘            │     │
│   │                                                                    │     │
│   │   Resource Impact: ~50MB RAM, <1% CPU (lightweight exporters)     │     │
│   └───────────────────────────────────────────────────────────────────┘     │
│                                                                              │
│                         All ports bound to 127.0.0.1                         │
│                                    │                                         │
│                             ┌──────┴──────┐                                  │
│                             │   OpenSSH   │◀─── Firewall allows port 22      │
│                             │    :22      │                                  │
│                             └──────┬──────┘                                  │
└────────────────────────────────────┼────────────────────────────────────────┘
                                     │
                              SSH Tunnel
                           (encrypted connection)
                                     │
┌────────────────────────────────────┼────────────────────────────────────────┐
│                             YOUR MAC (Monitoring)                            │
├────────────────────────────────────┼────────────────────────────────────────┤
│                                    │                                         │
│                             ┌──────┴──────┐                                  │
│                             │  tunnel.sh  │                                  │
│                             │   SSH -L    │                                  │
│                             └──────┬──────┘                                  │
│                                    │                                         │
│          ┌────── localhost:8000 ───┼─── localhost:5555 ──────┐              │
│          │       localhost:9187 ───┼─── localhost:9121       │              │
│          │                         │                         │              │
│          ▼                         ▼                         ▼              │
│   ┌─────────────┐           ┌─────────────┐          ┌─────────────┐        │
│   │ Prometheus  │──────────▶│   Grafana   │          │   Flower    │        │
│   │   :9090     │           │    :3000    │          │    :5555    │        │
│   │             │           │             │          │   (direct)  │        │
│   │ 90-day      │           │ Dashboards  │          │  Celery UI  │        │
│   │ retention   │           │ & Alerts    │          │             │        │
│   └─────────────┘           └─────────────┘          └─────────────┘        │
│                                                                              │
│                    No impact on Windows server performance                   │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Components

### On Windows Server (Lightweight)

| Component | Image | Purpose | Resource Impact |
|-----------|-------|---------|-----------------|
| **Flower** | `mher/flower:2.0` | Celery monitoring UI and Prometheus metrics | ~30MB RAM |
| **postgres-exporter** | `prometheuscommunity/postgres-exporter` | PostgreSQL metrics | ~10MB RAM |
| **redis-exporter** | `oliver006/redis_exporter` | Redis metrics | ~10MB RAM |
| **OpenSSH Server** | Windows built-in | Secure tunnel endpoint | Negligible |

### On Your Mac (Full Stack)

| Component | Image | Purpose |
|-----------|-------|---------|
| **Prometheus** | `prom/prometheus:v2.48.0` | Metrics collection and storage (90-day retention) |
| **Grafana** | `grafana/grafana:10.2.0` | Visualization, dashboards, alerting |

## Metrics Available

### API Metrics (`/metrics`)

| Metric | Description |
|--------|-------------|
| `http_requests_total` | Total HTTP requests by method, endpoint, status |
| `http_request_duration_seconds` | Request latency histogram |
| `http_requests_in_progress` | Currently active requests |

### Celery/Flower Metrics

| Metric | Description |
|--------|-------------|
| `flower_events_total{type="task-received"}` | Tasks received |
| `flower_events_total{type="task-succeeded"}` | Tasks completed successfully |
| `flower_events_total{type="task-failed"}` | Tasks failed |
| `flower_worker_online` | Number of online workers |

### PostgreSQL Metrics

| Metric | Description |
|--------|-------------|
| `pg_stat_activity_count` | Active database connections |
| `pg_database_size_bytes` | Database size |
| `pg_stat_user_tables_n_live_tup` | Row counts per table |
| `pg_stat_user_tables_seq_scan` | Sequential scans (index health) |

### Redis Metrics

| Metric | Description |
|--------|-------------|
| `redis_memory_used_bytes` | Current memory usage |
| `redis_connected_clients` | Connected client count |
| `redis_commands_processed_total` | Total commands processed |
| `redis_keyspace_hits_total` | Cache hit count |
| `redis_keyspace_misses_total` | Cache miss count |

## Quick Start

### 1. Deploy to Windows

The monitoring exporters are automatically deployed with the main application:

```bash
cd ansible
./run-playbook.sh deploy.yaml
```

This will:
- Install OpenSSH Server on Windows
- Open firewall port 22 for SSH
- Deploy Flower and metric exporters

### 2. Start SSH Tunnel (on Mac)

```bash
cd monitoring
./tunnel.sh your-username@windows-server-ip
```

Leave this terminal open. The tunnel forwards ports:
- 8000 → FastAPI + metrics
- 5555 → Flower
- 9187 → PostgreSQL exporter
- 9121 → Redis exporter

### 3. Start Monitoring Stack (on Mac)

```bash
cd monitoring
docker compose up -d
```

### 4. Access Dashboards

| Service | URL | Credentials |
|---------|-----|-------------|
| Grafana | http://localhost:3000 | admin / admin |
| Prometheus | http://localhost:9090 | - |
| Flower | http://localhost:5555 | admin / admin |

## Pre-Built Dashboard

A "Whisper Pipeline Overview" dashboard is automatically provisioned with:

- **Pending Tasks** - Current queue depth
- **Tasks Completed** - Total successful transcriptions
- **Tasks Failed** - Error count
- **Workers Online** - Active Celery workers
- **API Request Rate** - Requests per second
- **API Response Time** - 95th percentile latency
- **Redis Memory** - Broker memory usage
- **PostgreSQL Connections** - Active DB connections

## Alerts (Optional)

Example Grafana alert rules you can add:

```yaml
# High queue depth
- alert: HighQueueDepth
  expr: (flower_events_total{type="task-received"} - flower_events_total{type="task-succeeded"} - flower_events_total{type="task-failed"}) > 50
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "Task queue depth is high"

# No workers online
- alert: NoWorkersOnline
  expr: flower_worker_online == 0
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "No Celery workers are online"

# High API error rate
- alert: HighAPIErrorRate
  expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.1
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "API error rate is above 10%"
```

## Troubleshooting

### SSH Connection Refused

1. Verify OpenSSH Server is running on Windows:
   ```powershell
   Get-Service sshd
   ```

2. Check Windows Firewall:
   ```powershell
   Get-NetFirewallRule -Name "OpenSSH-Server-In-TCP"
   ```

3. Test SSH directly:
   ```bash
   ssh user@windows-server
   ```

### Prometheus Targets Show "DOWN"

1. Check if tunnel is connected:
   ```bash
   curl http://localhost:8000/metrics
   ```

2. If connection refused, restart the tunnel

3. Verify containers are running on Windows:
   ```powershell
   docker ps
   ```

### No Metrics in Grafana

1. Check Prometheus targets: http://localhost:9090/targets
2. Verify datasource configuration in Grafana
3. Check time range - default is "Last 1 hour"

### Tunnel Keeps Disconnecting

Install and use `autossh` for automatic reconnection:

```bash
# Install
brew install autossh

# Run with auto-reconnect
autossh -M 0 -o "ServerAliveInterval 30" -o "ServerAliveCountMax 3" -N \
    -L 8000:localhost:8000 \
    -L 5555:localhost:5555 \
    -L 9187:localhost:9187 \
    -L 9121:localhost:9121 \
    user@windows-server
```

## Security Notes

1. **SSH Keys**: For unattended operation, set up SSH key authentication instead of passwords
2. **Firewall**: Only port 22 is exposed on Windows; all other ports remain localhost-only
3. **Grafana**: Change the default password after first login
4. **Flower**: Uses basic auth configured via `FLOWER_AUTH` environment variable

## File Locations

| Location | Purpose |
|----------|---------|
| `monitoring/` | Mac-side monitoring stack |
| `monitoring/prometheus.yml` | Prometheus scrape configuration |
| `monitoring/provisioning/` | Grafana auto-provisioning |
| `docker-compose.yml` | Windows-side exporters (main compose) |
