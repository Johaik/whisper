# AI Agent Monitoring Tools

This document instructs AI agents (like Jules, Gemini CLI, or Antigravity) on how to query the production monitoring stack (Metrics and Logs) using the Grafana Cloud REST APIs or via the **Grafana MCP server**.

Since the environment has the Grafana MCP server connected, you can directly use the MCP tools instead of raw HTTP calls to inspect production health.

## Using the Grafana MCP Server

Agents can query metrics and logs directly using the provided tools.

### Querying Logs (Loki)
Use the `mcp_grafana_query_loki_logs` or `mcp_grafana_query_loki_stats` tools.

Your `datasourceUid` is standard for Loki hosted on Grafana Cloud. Generally, you can list the datasources first using `mcp_grafana_list_datasources` to find the exact UID for `grafanacloud-logs`.

**Example LogQL queries for this environment:**
- Application errors: `{job="windows_application_events"} |= "error"`
- FastAPI logs: `{service="api"}`

### Querying Metrics (Prometheus / Mimir)
Use the `mcp_grafana_query_prometheus` tool.

Similar to logs, list the datasources to find the exact UID for `grafanacloud-prom`.

**Example PromQL queries for this environment:**
- Windows CPU usage: `100 - (avg by (instance) (rate(windows_cpu_time_total{mode="idle"}[5m])) * 100)`
- API error rate: `rate(fastapi_responses_total{status_code=~"5.."}[5m])`

## Fallback: Direct API Queries

If MCP is unavailable, you can use the REST APIs directly via `curl`. 

**Credentials (from `mcp_config.json`):**
- Grafana URL: `https://johaik.grafana.net`
- API Key: `$GRAFANA_API_KEY` (Load from `.env`)

### REST Logging Example (Loki)
```bash
curl -G "https://logs-prod-06.grafana.net/loki/api/v1/query_range" \
  -u "1028045:$GRAFANA_API_KEY" \
  --data-urlencode 'query={service="api"}'
```

### REST Metrics Example (Mimir)
```bash
curl -G "https://prometheus-prod-36-prod-eu-north-0.grafana.net/api/v1/query" \
  -u "1863503:$GRAFANA_API_KEY" \
  --data-urlencode 'query=rate(fastapi_responses_total{status_code=~"5.."}[5m])'
```
