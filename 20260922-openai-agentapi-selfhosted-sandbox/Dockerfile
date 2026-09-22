FROM node:22-bookworm-slim

ARG IMAGE_MARKER=self-hosted-verifier-image
ENV SELF_HOSTED_IMAGE_MARKER=${IMAGE_MARKER}

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /workspace \
    && printf '%s\n' "${IMAGE_MARKER}" > /etc/self-hosted-image-marker \
    && npm install --global @openai/codex@alpha \
    && useradd --create-home --uid 10001 verifier \
    && chown -R verifier:verifier /workspace

COPY docker/entrypoint.sh /usr/local/bin/self-hosted-entrypoint
COPY runtime/AGENTS.md /workspace/AGENTS.md
COPY capabilities /workspace/capabilities
RUN chmod 0755 /usr/local/bin/self-hosted-entrypoint
RUN chown -R verifier:verifier /workspace

WORKDIR /workspace
USER verifier

# The controller supplies --remote and --environment-id and injects only
# CODEX_API_KEY at runtime.
ENTRYPOINT ["/usr/local/bin/self-hosted-entrypoint"]
