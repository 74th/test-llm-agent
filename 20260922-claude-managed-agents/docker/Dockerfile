# Self-hosted worker image for both container modes (see design.md D4).
# Mode A: `docker run <image> run`
# Mode B: `docker run <image> handle-item`
FROM python:3.12-slim

ARG IMAGE_IDENTIFIER=dev

# Verification marker: proves the agent's tool calls really executed inside
# this image, not Anthropic's cloud sandbox (self-hosted-environment spec).
RUN printf 'image=%s\nbuilt_at=%s\n' "$IMAGE_IDENTIFIER" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > /etc/cma-verification-marker

WORKDIR /app
COPY pyproject.toml ./
COPY common ./common
COPY worker ./worker

RUN pip install --no-cache-dir .

RUN mkdir -p /workspace
WORKDIR /workspace

ENTRYPOINT ["python", "-m", "worker"]
