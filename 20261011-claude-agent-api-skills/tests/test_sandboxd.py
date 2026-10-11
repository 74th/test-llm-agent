"""sandboxd クライアントのテスト(API キー不要。scripts/sandboxd_up.sh で起動しておく)。"""

import uuid
from pathlib import Path

import pytest

from verify.sandboxd import SandboxdClient

MARKER = "SANDBOXD-LOCAL-a91f"


@pytest.fixture(scope="module")
def sbx():
    c = SandboxdClient()
    if not c.health():
        pytest.skip("sandboxd が起動していない(scripts/sandboxd_up.sh)")
    yield c
    c.close()


def test_exec_python(sbx):
    r = sbx.exec("python3 -c 'print(1+1)'")
    assert r.ok and r.exit_code == 0
    assert r.stdout.strip() == "2"


def test_exec_default_cwd(sbx):
    assert sbx.exec("pwd").stdout.strip() == "/workspace"


def test_file_roundtrip(sbx):
    path = f"/workspace/tmp-{uuid.uuid4().hex[:8]}/a.txt"
    assert sbx.write(path, "こんにちは\n").ok
    r = sbx.read(path)
    assert r.ok and r.content == "こんにちは\n"
    names = [e["name"] for e in sbx.list(str(Path(path).parent)).entries]
    assert names == ["a.txt"]
    assert sbx.delete(str(Path(path).parent)).ok


def test_absolute_path_is_same_file_as_exec(sbx):
    # ファイル API の /workspace/x と、コマンドから見た /workspace/x が同じファイルであること
    d = f"/workspace/abs-{uuid.uuid4().hex[:8]}"
    assert sbx.write(f"{d}/x.txt", "same").ok
    assert sbx.exec(f"cat {d}/x.txt").stdout == "same"
    sbx.exec(f"echo fromexec > {d}/y.txt")
    assert sbx.read(f"{d}/y.txt").content == "fromexec\n"
    assert sbx.exec("ls /workspace").stdout.count("workspace") == 0
    sbx.delete(d)


def test_write_mode(sbx):
    path = f"tmp-{uuid.uuid4().hex[:8]}/run.sh"
    assert sbx.write(path, "#!/bin/sh\necho hi\n", mode="0755").ok
    r = sbx.exec(f"./{path}")
    assert r.ok and r.stdout.strip() == "hi"
    sbx.delete(str(Path(path).parent))


def test_marker_inside_and_not_on_host(sbx):
    r = sbx.exec("cat /etc/sandbox-marker")
    assert r.ok and r.stdout.strip() == MARKER
    assert not Path("/etc/sandbox-marker").exists()


def test_file_api_is_confined_to_root(sbx):
    # ファイル API では /etc/... は /workspace/etc/... と解釈され、root の外は読めない
    r = sbx.read("/etc/sandbox-marker")
    assert not r.ok and r.status == 404


def test_missing_file(sbx):
    r = sbx.read("/workspace/no/such/file.txt")
    assert not r.ok and r.status == 404 and r.error


def test_nonzero_exit(sbx):
    r = sbx.exec("echo oops >&2; exit 3")
    assert not r.ok and r.error is None
    assert r.exit_code == 3 and "oops" in r.stderr


def test_bad_cwd_is_result_not_exception(sbx):
    # /etc は /workspace/etc と解釈され、存在しないので gRPC エラーが結果として返る
    r = sbx.exec("pwd", cwd="/etc")
    assert not r.ok and r.exit_code == -1 and r.error



def test_probe_runs_in_sandbox(sbx):
    from verify.config import SKILL_DIR

    path = "probe-test/probe.py"
    assert sbx.write(path, (SKILL_DIR / "scripts/probe.py").read_bytes(), mode="0755").ok
    r = sbx.exec(f"python3 {path}")
    assert r.ok, r
    assert f"PROBE_MARKER: {MARKER}" in r.stdout
    assert "PROBE_SCRIPT: /workspace/probe-test/probe.py" in r.stdout
    assert "PROBE_CWD: /workspace" in r.stdout
    sbx.delete("probe-test")
