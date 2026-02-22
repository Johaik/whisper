import os
import requests
import json
import uuid
from dotenv import load_dotenv

load_dotenv()

GRAFANA_URL = "https://johaik.grafana.net"
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY", "")

def upload_dashboard(filepath):
    print(f"Uploading {filepath} to Grafana Cloud...")
    with open(filepath, 'r') as f:
        dashboard = json.load(f)
        
    dashboard['id'] = None
    if 'uid' not in dashboard or not dashboard['uid']:
        dashboard['uid'] = str(uuid.uuid4())[:8]

    headers = {
        "Authorization": f"Bearer {GRAFANA_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "dashboard": dashboard,
        "overwrite": True,
        "message": "Migrated from local provisioning"
    }

    resp = requests.post(f"{GRAFANA_URL}/api/dashboards/db", headers=headers, json=payload)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Success! Dashboard available at: {GRAFANA_URL}{data.get('url')}")
    else:
        print(f"❌ Failed: HTTP {resp.status_code}")
        print(resp.text)

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    dashboards_dir = os.path.join(project_root, "monitoring/provisioning/dashboards")
    for filename in os.listdir(dashboards_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(dashboards_dir, filename)
            upload_dashboard(filepath)
