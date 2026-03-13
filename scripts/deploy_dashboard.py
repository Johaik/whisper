import os
import requests
import json
import uuid
from dotenv import load_dotenv

# Load from project .env or local .env
load_dotenv()

# Defaults to the new cloud account provided by the user
GRAFANA_URL = os.getenv("GRAFANA_URL", "https://johai.grafana.net")
GRAFANA_API_KEY = os.getenv("GRAFANA_TOKEN", "")

def upload_dashboard(filepath):
    print(f"Uploading {filepath} to Grafana Cloud ({GRAFANA_URL})...")
    with open(filepath, 'r', encoding='utf-8') as f:
        dashboard = json.load(f)
        
    dashboard['id'] = None
    # We want to keep the UIDs consistent for cross-linking (grafanacloud-prom, etc)
    # The UIDs in our files match the new Grafana Cloud UIDs.

    headers = {
        "Authorization": f"Bearer {GRAFANA_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "dashboard": dashboard,
        "overwrite": True,
        "message": "Provisioned via whisper-pipeline"
    }

    resp = requests.post(f"{GRAFANA_URL}/api/dashboards/db", headers=headers, json=payload)
    if resp.status_code == 200:
        data = resp.json()
        print(f"✅ Success! Dashboard available at: {GRAFANA_URL}{data.get('url')}")
    else:
        print(f"❌ Failed: HTTP {resp.status_code}")
        print(resp.text)

if __name__ == "__main__":
    if not GRAFANA_API_KEY:
        print("❌ GRAFANA_TOKEN not found in environment. Please set it in your .env file.")
        exit(1)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    dashboards_dir = os.path.join(project_root, "monitoring/provisioning/dashboards")
    
    if not os.path.exists(dashboards_dir):
        print(f"❌ Dashboards directory not found: {dashboards_dir}")
        exit(1)

    for filename in os.listdir(dashboards_dir):
        if filename.endswith(".json"):
            filepath = os.path.join(dashboards_dir, filename)
            upload_dashboard(filepath)
