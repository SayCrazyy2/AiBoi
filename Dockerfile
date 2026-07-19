# Runs `ai serve` -- the production entrypoint that starts a health check
# endpoint (if $PORT is set) plus whichever bots have tokens configured via
# environment variables. Works as-is on Railway, Render, Fly.io, a bare VPS
# with Docker, or `docker run` locally.

FROM python:3.12-slim

# git: some MCP servers are installed/run via git. curl: handy for
# debugging inside the container / used by some MCP server installers.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir -e .

# Config/session/MCP state lives here so it survives restarts if you attach
# a persistent volume at /data (Railway: add a Volume mounted at /data).
ENV AI_CLI_HOME=/data/.ai-cli
ENV AI_CLI_NONINTERACTIVE=1
RUN mkdir -p /data

EXPOSE 8080

CMD ["ai", "serve"]
