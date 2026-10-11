# sandboxd(kubernetes-sigs/agent-sandbox, KEP-539.2)を固定タグからビルドし、
# Python 3 のイメージに載せる(design D1)。
ARG AGENT_SANDBOX_TAG=v1.0.6

FROM golang:1.27.1 AS builder
ARG AGENT_SANDBOX_TAG
WORKDIR /src
RUN git clone --depth 1 --branch ${AGENT_SANDBOX_TAG} https://github.com/kubernetes-sigs/agent-sandbox.git .
RUN go mod download
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w \
      -X sigs.k8s.io/agent-sandbox/internal/version.gitVersion=${AGENT_SANDBOX_TAG}" \
    -o /sandboxd ./packages/sandboxd/cmd/sandboxd

FROM python:3.13-slim
ARG SANDBOX_MARKER=SANDBOXD-LOCAL-a91f
# コマンドがこのコンテナで実行されたことを区別するためのマーカー(ホストには無い)
RUN printf '%s\n' "$SANDBOX_MARKER" > /etc/sandbox-marker
COPY --from=builder /sandboxd /usr/local/bin/sandboxd
RUN mkdir -p /workspace
WORKDIR /workspace
EXPOSE 8080 9090
ENTRYPOINT ["/usr/local/bin/sandboxd"]
CMD ["--root-dir=/workspace"]
