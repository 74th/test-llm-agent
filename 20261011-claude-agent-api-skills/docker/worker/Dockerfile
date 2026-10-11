# Managed Agents の self-hosted ワーカー(design D6)。ビルドコンテキストはリポジトリ直下。
FROM python:3.13-slim
ARG SANDBOX_MARKER=CMA-WORKER-LOCAL-5c2e
ARG ANTHROPIC_VERSION=1.13.0
# コマンドがこのコンテナで実行されたことを区別するためのマーカー(ホストには無い)
RUN printf '%s\n' "$SANDBOX_MARKER" > /etc/sandbox-marker
RUN pip install --no-cache-dir "anthropic==${ANTHROPIC_VERSION}"
COPY src/verify/worker_main.py /app/worker_main.py
RUN mkdir -p /workspace
WORKDIR /workspace
ENTRYPOINT ["python", "/app/worker_main.py"]
