import sqlite3
import pytest
from poc.repository import ThreadRepository

def test_crud_isolation_and_restart(tmp_path):
    path = tmp_path / "threads.sqlite3"
    repo = ThreadRepository(path)
    a, b = repo.create_thread("A"), repo.create_thread("B")
    repo.add_message(a["id"], "user", "Aだけ")
    repo.add_message(b["id"], "user", "Bだけ")
    reopened = ThreadRepository(path)
    assert [m["content"] for m in reopened.get_thread(a["id"])["messages"]] == ["Aだけ"]
    assert [m["content"] for m in reopened.get_thread(b["id"])["messages"]] == ["Bだけ"]
    assert {item["id"] for item in reopened.list_threads()} == {a["id"], b["id"]}

def test_running_run_becomes_interrupted_after_restart(tmp_path):
    path = tmp_path / "threads.sqlite3"
    repo = ThreadRepository(path)
    thread = repo.create_thread()
    repo.begin_run(thread["id"], "run-1")
    assert ThreadRepository(path).get_thread(thread["id"])["lastRunStatus"] == "interrupted"

def test_one_active_run_per_thread(tmp_path):
    repo = ThreadRepository(tmp_path / "threads.sqlite3")
    thread = repo.create_thread()
    repo.begin_run(thread["id"], "run-1")
    with pytest.raises(RuntimeError, match="active run"):
        repo.begin_run(thread["id"], "run-2")
