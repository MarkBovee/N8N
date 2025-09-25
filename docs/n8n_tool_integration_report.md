## n8n webhook / proxy integration — findings & next steps

Date: 2025-09-25

### Purpose

Short, shareable record of what I tested, what failed, and recommended next steps so you can pick this up later.

---

### Summary of what I did

- Updated `TOOL_REGISTRY_JSON` in the repo `.env` to map local tool names to the discovered n8n webhook path.
- Rebuilt and restarted the Docker Compose stack so the proxy would pick up the mapping.
- Ran the test client `scripts/post_with_tools.py` to exercise tool calls through the proxy.
- Instrumented container-internal calls (from the `github-models-proxy` container) and host curl requests to validate reachability.
- Collected proxy and n8n logs during the test run.

### Key findings

- The proxy correctly preserved upstream `tool_calls` and attempted to execute them via the `TOOL_REGISTRY_JSON` mapping.
- The proxy POSTed to: `http://n8n:5678/webhook/90f0993e-31ff-4523-8dbc-613465d12b64/chat` but n8n responded with 404 Not Found.
- Direct testing from the host and from inside the `github-models-proxy` container returned the same 404 for both GET and POST.
- n8n REST API confirms the workflow `PPQEG0yLOImvSmCM` exists, is active, and the node `When chat message received` has `webhookId: 90f0993e-31ff-4523-8dbc-613465d12b64`.
- n8n container logs show the workflow activation message but also show repeated `Received SIGTERM` / `Stopping n8n` / `n8n ready` messages earlier in the session — which suggests runtime instability or restarts while testing.

### Evidence (selected log & responses)

- Proxy attempted tool call and received 404:

  - Proxy log: POST http://n8n:5678/webhook/90f0993e-31ff-4523-8dbc-613465d12b64/chat -> HTTP/1.1 404 Not Found

- Host curl directly to webhook:

  - `curl -v -X POST http://localhost:5678/webhook/90f0993e-31ff-4523-8dbc-613465d12b64/chat` → HTTP/1.1 404 Not Found

- Proxy container-internal check (from `github-models-proxy`):

  - `docker compose exec github-models-proxy sh -c 'curl -D - -o - -s http://n8n:5678/webhook/90f0993e-31ff-4523-8dbc-613465d12b64/chat'` → HTTP/1.1 404 Not Found

- Workflow REST response (truncated):

  - `GET /api/v1/workflows/PPQEG0yLOImvSmCM` returned JSON including `webhookId: "90f0993e-31ff-4523-8dbc-613465d12b64"` and node `When chat message received`.

- n8n logs show activation + repeated shutdown/start messages (SIGTERM) — see n8n container logs for repeated sequences of:

  - "Received SIGTERM. Shutting down..."
  - "Stopping n8n..."
  - "n8n ready on ::, port 5678"

### Root-cause hypothesis

The proxy and mapping are working. The immediate cause of the 404 is most likely that the n8n runtime did not have the webhook handler registered at the time of the request: either because n8n was restarting during tests or because the webhook route was not active on the running instance. The DB contains the webhook row, but the runtime registration can lag or fail if the process restarts.

Less likely possibilities (but worth checking): path mismatch (trailing slash, base path), method mismatch, or webhook protection (headers/basic auth). However the workflow shows both GET and POST entries for that webhookId.

### Short-term next steps (pick one and run)

1. Verify runtime stability and why n8n SIGTERM occurs
   - Tail the `n8n` logs and investigate what is triggering SIGTERM (resource limits, host signals, or manual restarts). If n8n is unstable, fix that and re-test.

2. Confirm DB webhook_entity rows (deterministic check)
   - Run a Postgres query to dump rows for `workflowId='PPQEG0yLOImvSmCM'` and confirm `webhookPath`, `method`, and `node`:

     ```powershell
     docker compose exec postgres psql -U n8n -d n8n -c "SELECT id, workflowId, webhookPath, method, node FROM webhook_entity WHERE \"workflowId\"='PPQEG0yLOImvSmCM';"
     ```

3. If runtime is stable but 404 persists
   - Try calling the webhook with a trailing slash or different HTTP method.
   - Try adding headers (if you expect Basic Auth or other protection).
   - Create a minimal new workflow with an HTTP webhook node (simple echo) to confirm webhook registration and route handling independently.

4. Add header support to `TOOL_REGISTRY_JSON` (optional)
   - If the webhook requires an auth header, change mapping entries to accept an object with `url` and `headers`. This requires a small code update to `proxy_server/tool_handler.py` (I can do it if you want).

### How to pick this up later (quick checklist)

- Rebuild and restart the stack after any change so the proxy picks up `.env`:

  ```powershell
  docker compose up -d --build
  ```

- Run the end-to-end test again:

  ```powershell
  python scripts/post_with_tools.py
  ```

- If failure repeats, collect these logs for diagnosis and paste them into this file or the issue:
  - `docker compose logs github-models-proxy --tail 200`
  - `docker compose logs n8n --tail 300`
  - `docker compose exec github-models-proxy sh -c 'curl -v -X POST http://n8n:5678/webhook/<id>/chat -d "{\"test\":1}"'`

### Notes & context

- `TOOL_REGISTRY_JSON` was set to:

  ```json
  {"echo":"http://n8n:5678/webhook/90f0993e-31ff-4523-8dbc-613465d12b64/chat","When chat message received":"http://n8n:5678/webhook/90f0993e-31ff-4523-8dbc-613465d12b64/chat","chat":"http://n8n:5678/webhook/90f0993e-31ff-4523-8dbc-613465d12b64/chat"}
  ```

- The proxy will return function-role messages even on tool-run failures (the tool-runner intentionally returns a function-style message with the error text so the upstream model receives a usable follow-up rather than a 500).

---

If you want, I can add a short script to automatically generate `TOOL_REGISTRY_JSON` from `webhook_entity` rows so mapping is repeatable — say the word and I'll add it.
