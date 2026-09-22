import json

from orchestrator.lifecycle_log import log_event


def test_each_line_is_independently_valid_json(tmp_path):
    path = tmp_path / "container-lifecycle.jsonl"

    log_event("container_start", path=path, session_id="s1", work_id="w1", container_name="cma-w1")
    log_event(
        "container_exit",
        path=path,
        session_id="s1",
        work_id="w1",
        container_name="cma-w1",
        exit_code=0,
        duration_ms=1234,
        error=None,
    )

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    records = [json.loads(line) for line in lines]

    assert records[0]["event"] == "container_start"
    assert records[0]["work_id"] == "w1"
    assert "ts" in records[0]

    assert records[1]["event"] == "container_exit"
    assert records[1]["exit_code"] == 0
    assert records[1]["container_name"] == records[0]["container_name"]


def test_creates_parent_directory(tmp_path):
    path = tmp_path / "nested" / "dir" / "log.jsonl"
    log_event("container_start", path=path, work_id="w1")
    assert path.exists()
