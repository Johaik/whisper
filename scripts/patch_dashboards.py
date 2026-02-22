import json
import os

LOGS_DB = "monitoring/provisioning/dashboards/whisper-logs-overview.json"

def patch_logs_dashboard():
    with open(LOGS_DB, 'r') as f:
        data = json.load(f)
        
    dashboard = data.get("dashboard", data)
    if "templating" not in dashboard:
        dashboard["templating"] = {"list": []}
        
    # Check if app_service and job variables exist already
    var_names = [v.get("name") for v in dashboard["templating"]["list"]]
    
    app_service_var = {
            "name": "app_service",
            "type": "query",
            "datasource": {"uid": "grafanacloud-logs", "type": "loki"},
            "query": "label_values({job=\"docker_containers\"}, app_service)",
            "refresh": 1,
            "sort": 1,
            "multi": True,
            "includeAll": True,
            "allValue": ".*"
    }
    
    if "app_service" in var_names:
        idx = var_names.index("app_service")
        dashboard["templating"]["list"][idx] = app_service_var
    else:
        dashboard["templating"]["list"].append(app_service_var)
        
    if "job" not in var_names:
         dashboard["templating"]["list"].append({
            "name": "job",
            "type": "custom",
            "query": "docker_containers,windows_application_events,windows_system_events",
            "multi": True,
            "includeAll": True,
            "allValue": ".*",
            "current": {"text": "All", "value": ["$__all"]},
            "options": [
                {"text": "All", "value": "$__all", "selected": True},
                {"text": "docker_containers", "value": "docker_containers", "selected": False},
                {"text": "windows_application_events", "value": "windows_application_events", "selected": False},
                {"text": "windows_system_events", "value": "windows_system_events", "selected": False}
            ]
        })

    # Update panels
    for panel in dashboard.get("panels", []):
        if "Docker" in panel.get("title", ""):
            if "targets" in panel and len(panel["targets"]) > 0:
                panel["targets"][0]["expr"] = '{job="docker_containers", app_service=~"$app_service"}'
                
    with open(LOGS_DB, 'w') as f:
        json.dump(dashboard, f, indent=2)

METRICS_DB = "monitoring/provisioning/dashboards/whisper-overview.json"

def patch_metrics_dashboard():
    with open(METRICS_DB, 'r') as f:
        data = json.load(f)
        
    dashboard = data.get("dashboard", data)
    
    # Update panels
    for panel in dashboard.get("panels", []):
        if "datasource" in panel and isinstance(panel["datasource"], dict):
            if panel["datasource"].get("uid") == "${datasource}" or panel["datasource"].get("type") == "prometheus":
                panel["datasource"]["uid"] = "grafanacloud-prom"

        if "targets" in panel:
            for target in panel["targets"]:
                if "datasource" in target and isinstance(target["datasource"], dict):
                    if target["datasource"].get("uid") == "${datasource}" or target["datasource"].get("type") == "prometheus":
                        target["datasource"]["uid"] = "grafanacloud-prom"
                
                expr = target.get("expr", "")
                if 'job="whisper-api"' in expr:
                    target["expr"] = expr.replace('job="whisper-api"', 'service="api"')
                
    with open(METRICS_DB, 'w') as f:
        json.dump(dashboard, f, indent=2)

patch_logs_dashboard()
patch_metrics_dashboard()
print("Patched logs and metrics dashboards.")
