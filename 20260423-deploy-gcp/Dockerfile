FROM debian:12-slim

RUN groupadd -g 1000 user && \
    useradd -r -u 1000 -g user user

# install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_PYTHON_INSTALL_DIR=/var/uv/python
ENV UV_CACHE_DIR=/var/uv/cache

WORKDIR /app

COPY .python-version \
    uv.lock \
    pyproject.toml \
    .

RUN  uv sync --frozen --no-install-project

COPY hello_agent ./hello_agent

USER 1000

ENTRYPOINT [".venv/bin/python", "-m", "hello_agent"]
