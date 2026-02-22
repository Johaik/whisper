import os
import requests
import json
import uuid
from dotenv import load_dotenv

load_dotenv()

GRAFANA_URL = "https://johaik.grafana.net"
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY", "")
LOKI_UID = "grafanacloud-logs" # From MCP datasource check

logs_dashboard = {
    "title": "Windows & Application Logs Overview",
    "uid": "whisper-logs-overview",
    "tags": ["logs", "windows", "whisper"],
    "timezone": "browser",
    "schemaVersion": 38,
    "panels": [
        {
            "title": "Windows Application Events (Errors & Warnings)",
            "type": "logs",
            "datasource": {"type": "loki", "uid": LOKI_UID},
            "gridPos": {"h": 12, "w": 24, "x": 0, "y": 0},
            "targets": [
                {
                    "expr": '{job="windows_application_events"} |= "error" or "warn"',
                    "refId": "A"
                }
            ],
            "options": {
                "showLabels": True,
                "showTime": True,
                "wrapLogMessage": True,
                "sortOrder": "Descending"
            }
        },
        {
            "title": "Docker/FastAPI Application Logs",
            "type": "logs",
            "datasource": {"type": "loki", "uid": LOKI_UID},
            "gridPos": {"h": 12, "w": 24, "x": 0, "y": 12},
            "targets": [
                {
                    "expr": '{service=~"api|celery"}',
                    "refId": "A"
                }
            ],
             "options": {
                "showLabels": True,
                "showTime": True,
                "wrapLogMessage": True,
                "sortOrder": "Descending"
            }
        }
    ]
}

def upload_logs_dashboard():
    print("Uploading Logs Dashboard to Grafana Cloud...")
    headers = {
        "Authorization": f"Bearer {GRAFANA_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "dashboard": logs_dashboard,
        "overwrite": True,
        "message": "Auto-generated Logs dashboard"
    }

    resp = requests.post(f"{GRAFANA_URL}/api/dashboards/db", headers=headers, json=payload)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Success! Dashboard available at: {GRAFANA_URL}{data.get('url')}")
    else:
        print(f"❌ Failed: HTTP {resp.status_code}")
        print(resp.text)

if __name__ == "__main__":
    upload_logs_dashboard()
