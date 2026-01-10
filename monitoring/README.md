# Whisper Monitoring Stack

Remote monitoring for the Whisper Transcription Pipeline running on Windows, accessed via SSH tunnel from your Mac.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         WINDOWS SERVER                                   │
│                                                                          │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│   │  FastAPI    │  │   Flower    │  │  Postgres   │  │   Redis     │   │
│   │   :8000     │  │   :5555     │  │  Exporter   │  │  Exporter   │   │
│   │  /metrics   │  │  /metrics   │  │   :9187     │  │   :9121     │   │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘   │
│          │                │                │                │          │
│          └────────────────┴────────────────┴────────────────┘          │
│                                    │                                    │
│                              localhost only                             │
│                                    │                                    │
│                             ┌──────┴──────┐                             │
│                             │   OpenSSH   │                             │
│                             │    :22      │                             │
│                             └──────┬──────┘                             │
└────────────────────────────────────┼────────────────────────────────────┘
                                     │
                              SSH Tunnel
                                     │
┌────────────────────────────────────┼────────────────────────────────────┐
│                             YOUR MAC                                     │
│                                    │                                     │
│                             ┌──────┴──────┐                             │
│                             │   tunnel.sh │                             │
│                             │  (SSH -L)   │                             │
│                             └──────┬──────┘                             │
│                                    │                                     │
│          ┌─────────────────────────┴─────────────────────────┐          │
│          │                                                    │          │
│   ┌──────┴──────┐                                     ┌───────┴───────┐ │
│   │ Prometheus  │─────────────────────────────────────│   Grafana     │ │
│   │   :9090     │                                     │    :3000      │ │
│   │             │        scrapes via tunnel           │               │ │
│   └─────────────┘                                     └───────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Start the SSH Tunnel

```bash
cd monitoring
./tunnel.sh your-username@windows-server-ip
```

Keep this terminal open - the tunnel needs to stay connected.

### 2. Start Monitoring Stack

In a new terminal:

```bash
cd monitoring
docker compose up -d
```

### 3. Access Dashboards

- **Grafana**: http://localhost:3000 (admin/admin)
- **Prometheus**: http://localhost:9090
- **Flower** (direct): http://localhost:5555

## What's Monitored

| Component | Metrics | Port |
|-----------|---------|------|
| FastAPI API | Request rate, latency, error rates | 8000 |
| Celery Workers | Task queue, active tasks, failures | 5555 |
| PostgreSQL | Connections, query performance | 9187 |
| Redis | Memory usage, commands, hit ratio | 9121 |

## Files

```
monitoring/
├── docker-compose.yml          # Prometheus + Grafana
├── prometheus.yml              # Scrape configuration
├── tunnel.sh                   # SSH tunnel helper script
├── README.md                   # This file
└── provisioning/
    ├── datasources/
    │   └── datasource.yml      # Auto-configure Prometheus datasource
    └── dashboards/
        ├── dashboard.yml       # Dashboard provisioning config
        └── whisper-overview.json  # Pre-built overview dashboard
```

## Troubleshooting

### Can't connect to metrics endpoints

1. Check if the SSH tunnel is still running
2. Verify you can reach the Windows server: `ssh user@windows-server`
3. On Windows, verify services are running: `docker ps`

### No data in Grafana

1. Check Prometheus targets: http://localhost:9090/targets
2. All targets should show "UP" status
3. If "DOWN", the tunnel may have disconnected

### Tunnel keeps disconnecting

Use autossh for automatic reconnection:

```bash
# Install autossh
brew install autossh

# Use autossh instead of ssh
autossh -M 0 -N \
    -L 8000:localhost:8000 \
    -L 5555:localhost:5555 \
    -L 9187:localhost:9187 \
    -L 9121:localhost:9121 \
    user@windows-server
```

### Reset Grafana password

```bash
docker compose exec grafana grafana-cli admin reset-admin-password newpassword
```

## Adding Custom Dashboards

1. Create dashboards in Grafana UI
2. Export as JSON (Share → Export → Save to file)
3. Save to `provisioning/dashboards/`
4. Restart Grafana: `docker compose restart grafana`
