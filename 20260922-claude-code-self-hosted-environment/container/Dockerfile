FROM debian:bookworm-slim

ARG CLAUDE_CODE_VERSION
ARG TARGETARCH

RUN apt-get update && apt-get install -y --no-install-recommends \
      git curl ca-certificates openssh-client jq gnupg \
 && rm -rf /var/lib/apt/lists/*

# google-cloud-sdk (bq / gcloud) — needed at session runtime so a session can
# write and run its own BigQuery access script (container-execution-evidence).
RUN echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
      > /etc/apt/sources.list.d/google-cloud-sdk.list \
 && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
      | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg \
 && apt-get update && apt-get install -y --no-install-recommends google-cloud-cli \
 && rm -rf /var/lib/apt/lists/*

# docker-ce-cli only (no daemon) — needed by provisioners/docker.sh when this
# image runs as the Mode B orchestrator, which spawns sibling session
# containers over the mounted host docker.sock (design.md D7).
RUN install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
 && rm -rf /var/lib/apt/lists/*

# uv — lets a session run ad-hoc Python scripts (e.g. `uv run --with
# google-cloud-bigquery script.py`) without a pre-baked venv, so
# container-execution-evidence prompts (task 9.1 (e)) don't have to fall
# back to the bq CLI for lack of a Python toolchain.
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

RUN arch="${TARGETARCH:-amd64}" \
 && case "$arch" in \
      amd64) claude_arch=linux-x64 ;; \
      arm64) claude_arch=linux-arm64 ;; \
      *) echo "unsupported arch: $arch" >&2; exit 1 ;; \
    esac \
 && curl -fsSL "https://downloads.claude.ai/claude-code-releases/${CLAUDE_CODE_VERSION:?set with --build-arg CLAUDE_CODE_VERSION}/${claude_arch}/claude" \
      -o /usr/local/bin/claude \
 && chmod +x /usr/local/bin/claude

# System-scope git identity: the runner process's own user, whichever uid it
# runs as, needs an identity for any commit, and safe.directory covers
# checkouts owned by a different uid (D4 in design.md).
RUN git config --system user.name "Claude" \
 && git config --system user.email "noreply@anthropic.com" \
 && git config --system --add safe.directory '*'

# D1 in design.md: HOME becomes the runner's writable config root, so
# ~/.claude and ~/.claude.json land exactly where the docs' default (unset
# SELF_HOSTED_RUNNER_HOST_CONFIG_DIR) reads them from.
ENV HOME=/opt/claude-config
RUN mkdir -p /opt/claude-config

COPY entrypoint.sh /opt/claude/entrypoint.sh
COPY session-wrapper.sh /opt/claude/session-wrapper.sh
COPY log-event.sh /opt/claude/log-event.sh
COPY hooks/spawn-runner /opt/claude/hooks/spawn-runner
COPY hooks/post-session /opt/claude/hooks/post-session
COPY provisioners/docker.sh /opt/claude/provisioners/docker.sh
COPY checkout-probe/checkout /opt/claude/checkout-probe/checkout
RUN chmod +x /opt/claude/entrypoint.sh /opt/claude/session-wrapper.sh /opt/claude/log-event.sh \
      /opt/claude/hooks/spawn-runner /opt/claude/hooks/post-session \
      /opt/claude/provisioners/docker.sh /opt/claude/checkout-probe/checkout

ENTRYPOINT ["/opt/claude/entrypoint.sh"]
