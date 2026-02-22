import os
import requests
import json
import base64
from dotenv import load_dotenv

load_dotenv()

# Settings based on mcp_config.json
PROMETHEUS_URL = "https://prometheus-prod-53-prod-me-central-1.grafana.net/api/prom/api/v1/query"
LOKI_URL = "https://logs-prod-033.grafana.net/loki/api/v1/query_range"
GRAFANA_API_KEY = os.getenv("GRAFANA_API_KEY", "")

PROM_USER = "2992950"
LOKI_USER = "1492150"

def _get_auth_header(user, password):
    token = f"{user}:{password}".encode("utf-8")
    encoded_token = base64.b64encode(token).decode("utf-8")
    return {"Authorization": f"Basic {encoded_token}"}

def test_prometheus():
    print("Testing Prometheus/Mimir API...")
    query = "100 - (avg by (instance) (rate(windows_cpu_time_total{mode='idle'}[5m])) * 100)"
    headers = _get_auth_header(PROM_USER, GRAFANA_API_KEY)
    
    try:
        response = requests.get(PROMETHEUS_URL, headers=headers, params={"query": query})
        response.raise_for_status()
        data = response.json()
        print(f"✅ Success! Response Status: {data.get('status')}")
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        if status_code == 401:
          print(f"❌ Failed: Unauthorized. Please verify your credentials or ensure the server is configured to accept queries.")
        else:
          print(f"❌ Failed: HTTP Error {status_code}: {e.response.text}")
    except Exception as e:
        print(f"❌ Failed: {e}")

def test_loki():
    print("\nTesting Loki API...")
    query = '{service="api"}'
    headers = _get_auth_header(LOKI_USER, GRAFANA_API_KEY)
    
    try:
        # Minimal query range request
        response = requests.get(LOKI_URL, headers=headers, params={"query": query, "limit": 1})
        response.raise_for_status()
        data = response.json()
        print(f"✅ Success! Response Status: {data.get('status')}")
    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code
        if status_code == 401:
          print(f"❌ Failed: Unauthorized. Please verify your credentials.")
        else:
          print(f"❌ Failed: HTTP Error {status_code}: {e.response.text}")
    except Exception as e:
        print(f"❌ Failed: {e}")

if __name__ == "__main__":
    print("--- Grafana Cloud Agent API Test ---")
    test_prometheus()
    test_loki()
    print("------------------------------------")
