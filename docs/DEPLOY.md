# Deploy (Fly.io)

Four pieces: **Postgres (pgvector)**, the **MCP tools server**, the **agent**
(FastAPI), and the **web** console. The agent and web are public; the MCP server
is reached only over Fly private networking.

> Needs a Fly.io account + [`flyctl`](https://fly.io/docs/flyctl/install/). All
> commands run from the repo root. App names below match `ops/fly/*.fly.toml`.

```bash
flyctl auth login
```

## 1. Postgres + pgvector

```bash
flyctl postgres create --name oncallpilot-db --region fra --vm-size shared-cpu-1x --volume-size 1
# enable the extension + note the connection string
flyctl postgres connect -a oncallpilot-db -c "CREATE EXTENSION IF NOT EXISTS vector;"
```

Fly prints a `DATABASE_URL` when the cluster is created — keep it (it looks like
`postgres://postgres:<pw>@oncallpilot-db.flycast:5432/postgres`). If the image
lacks pgvector, deploy `pgvector/pgvector:pg16` as a Fly app with a volume
instead and use its URL.

## 2. Create the apps

```bash
flyctl apps create oncallpilot-mcp
flyctl apps create oncallpilot-agent
flyctl apps create oncallpilot-web
```

## 3. Agent secrets

```bash
flyctl secrets set -a oncallpilot-agent \
  ANTHROPIC_API_KEY="sk-ant-…" \
  DATABASE_URL="postgres://…@oncallpilot-db.flycast:5432/postgres" \
  MCP_URL="http://oncallpilot-mcp.flycast/mcp" \
  CORS_ALLOW_ORIGINS="https://oncallpilot-web.fly.dev" \
  DEMO_API_KEY="$(openssl rand -hex 16)" \
  DAILY_SPEND_CAP_USD="5.0"
```

`DEMO_API_KEY` + `DAILY_SPEND_CAP_USD` protect a public, unauthenticated demo from
running up your Claude bill (the edge guard). The web must send the same demo key
(step 5).

## 4. Deploy MCP, then the agent

The agent's image bakes the embedding model (~2 GB) — give it a machine with room.

```bash
flyctl deploy --config ops/fly/mcp.fly.toml   --dockerfile services/mcp-server/Dockerfile --remote-only
flyctl deploy --config ops/fly/agent.fly.toml --dockerfile services/agent/Dockerfile     --remote-only
flyctl scale memory 2048 -a oncallpilot-agent      # torch + bge-large need headroom
```

## 5. Deploy the web

`NEXT_PUBLIC_*` is baked at build time, so pass the agent URL (and demo key) as
build args:

```bash
flyctl deploy --config ops/fly/web.fly.toml --dockerfile apps/web/Dockerfile --remote-only \
  --build-arg NEXT_PUBLIC_AGENT_BASE_URL=https://oncallpilot-agent.fly.dev \
  --build-arg NEXT_PUBLIC_DEMO_API_KEY=<the DEMO_API_KEY from step 3>
```

## 6. Schema + ingest the corpus

Run ingest from **local** (which has the corpus + models) against the Fly
database through a proxy tunnel:

```bash
flyctl proxy 55432:5432 -a oncallpilot-db &          # tunnel Fly PG -> localhost:55432
export DATABASE_URL="postgresql://postgres:<pw>@localhost:55432/postgres"

# apply schema, then ingest
psql "$DATABASE_URL" -f services/agent/app/retrieval/schema.sql
cd services/agent && uv run python -m app.retrieval.ingest && cd -
kill %1                                              # close the tunnel
```

## 7. Verify

```bash
curl https://oncallpilot-agent.fly.dev/readyz          # {"status":"ready"}
```

Open **https://oncallpilot-web.fly.dev** — Ask for a cited answer, Act to reach an
approval gate, `metrics →` for the dashboard.

## CI

`.github/workflows/deploy.yml` runs steps 4–5 on a `v*` git tag when the repo
secret `FLY_API_TOKEN` is set (`flyctl tokens create deploy`). Postgres + ingest
(steps 1, 6) are one-time and stay manual.

## Notes

- The agent runs a single uvicorn worker by design: the HITL checkpointer and the
  edge-guard counters are in-process (see `DECISIONS.md`). Scale up = a shared
  store (Postgres checkpointer / Redis), not more workers.
- To keep costs near zero when idle, `oncallpilot-web` auto-stops; the agent and
  MCP stay warm (SSE + MCP sessions).
