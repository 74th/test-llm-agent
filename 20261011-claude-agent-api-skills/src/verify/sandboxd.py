"""sandboxd(gRPC ProcessService + HTTP FilesystemService)の小さなクライアント。

失敗は例外にせず、結果(ok / エラー内容)として返す(spec: 失敗の伝達)。
sandboxd はコマンドを argv として実行するので、シェル文字列は `/bin/sh -c` で包む。
ファイルのパスは `--root-dir`(/workspace)からの相対パスとして解釈される。
`/workspace/...` の絶対パスは root からの相対に読み替えられ、それ以外の絶対パス
(例 `/etc/x`)は `/workspace/etc/x` として扱われる(root の外には出られない)。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from urllib.parse import quote

import grpc
import httpx

from .sandboxd_pb.process.v1 import process_pb2, process_pb2_grpc

ROOT_DIR = "/workspace"


@dataclass
class ExecResult:
    exit_code: int
    stdout: str
    stderr: str
    error: str | None = None  # gRPC のエラー(コマンド自体が起動しなかったなど)

    @property
    def ok(self) -> bool:
        return self.error is None and self.exit_code == 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FileResult:
    ok: bool
    status: int
    content: str | None = None
    error: str | None = None
    entries: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


class SandboxdClient:
    def __init__(self, host: str = "127.0.0.1", grpc_port: int = 9090, rest_port: int = 8080, timeout: float = 60):
        self._channel = grpc.insecure_channel(f"{host}:{grpc_port}")
        self._stub = process_pb2_grpc.ProcessServiceStub(self._channel)
        self._http = httpx.Client(base_url=f"http://{host}:{rest_port}", timeout=timeout)
        self._timeout = timeout

    def close(self) -> None:
        self._channel.close()
        self._http.close()

    def __enter__(self) -> "SandboxdClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def health(self) -> bool:
        try:
            return self._http.get("/v1/health").json().get("status") == "ok"
        except httpx.HTTPError:
            return False

    def exec(self, command: str, cwd: str | None = ROOT_DIR) -> ExecResult:
        cfg = process_pb2.ProcessConfig(command=["/bin/sh", "-c", command])
        if cwd:
            cfg.cwd = cwd
        try:
            res = self._stub.Execute(process_pb2.ExecuteRequest(config=cfg), timeout=self._timeout)
        except grpc.RpcError as e:
            return ExecResult(-1, "", "", error=f"{e.code().name}: {e.details()}")
        return ExecResult(
            res.exit_code,
            res.stdout.decode(errors="replace"),
            res.stderr.decode(errors="replace"),
        )

    @staticmethod
    def _url(path: str) -> str:
        # URL の {path} は root からの相対パスとして解釈されるので、`/workspace/` の接頭辞を外す。
        # それ以外の絶対パスは、sandboxd と同じく root からの相対として扱う。
        if path == ROOT_DIR or path.startswith(ROOT_DIR + "/"):
            path = path[len(ROOT_DIR) :]
        return "/v1/files/" + quote(path.lstrip("/"), safe="/")

    def _error(self, r: httpx.Response) -> str:
        try:
            body = r.json()
            return f"{body.get('code')}: {body.get('message')}"
        except ValueError:
            return r.text

    def read(self, path: str) -> FileResult:
        try:
            r = self._http.get(self._url(path))
        except httpx.HTTPError as e:
            return FileResult(False, -1, error=str(e))
        if r.status_code != 200:
            return FileResult(False, r.status_code, error=self._error(r))
        if r.headers.get("content-type", "").startswith("application/json"):
            # ディレクトリを読んだ場合は一覧が返る
            return FileResult(False, r.status_code, error="is a directory", entries=r.json().get("entries", []))
        return FileResult(True, r.status_code, content=r.content.decode(errors="replace"))

    def write(self, path: str, content: str | bytes, mode: str | None = None) -> FileResult:
        params = {"mode": mode} if mode else None
        data = content.encode() if isinstance(content, str) else content
        try:
            r = self._http.put(self._url(path), content=data, params=params)
        except httpx.HTTPError as e:
            return FileResult(False, -1, error=str(e))
        if r.status_code not in (200, 201, 204):
            return FileResult(False, r.status_code, error=self._error(r))
        return FileResult(True, r.status_code)

    def list(self, path: str) -> FileResult:
        try:
            r = self._http.get(self._url(path))
        except httpx.HTTPError as e:
            return FileResult(False, -1, error=str(e))
        if r.status_code != 200:
            return FileResult(False, r.status_code, error=self._error(r))
        if not r.headers.get("content-type", "").startswith("application/json"):
            return FileResult(False, r.status_code, error="not a directory")
        return FileResult(True, r.status_code, entries=r.json().get("entries", []))

    def delete(self, path: str, recursive: bool = True) -> FileResult:
        try:
            r = self._http.delete(self._url(path), params={"recursive": str(recursive).lower()})
        except httpx.HTTPError as e:
            return FileResult(False, -1, error=str(e))
        return FileResult(r.status_code in (200, 204), r.status_code, error=None if r.status_code in (200, 204) else self._error(r))
