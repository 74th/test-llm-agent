"""検証用スキル sandbox-probe の単体テスト(API を使わない)。"""

import subprocess
import sys

from verify.config import SKILL_DIR

PASSPHRASE = "KUMQUAT-7412"


def test_skill_files_exist():
    for rel in ("SKILL.md", "reference.md", "scripts/probe.py"):
        assert (SKILL_DIR / rel).is_file(), rel


def test_skill_md_does_not_leak_answers():
    body = (SKILL_DIR / "SKILL.md").read_text()
    assert PASSPHRASE not in body
    assert "KUMQUAT" not in body
    assert "sandbox-marker" not in body
    assert "SANDBOXD-" not in body


def test_reference_has_passphrase():
    assert PASSPHRASE in (SKILL_DIR / "reference.md").read_text()


def test_probe_on_host():
    out = subprocess.run(
        [sys.executable, str(SKILL_DIR / "scripts/probe.py")], capture_output=True, text=True, check=True
    ).stdout.splitlines()
    keys = [line.split(":", 1)[0] for line in out]
    assert keys == ["PROBE_HOST", "PROBE_MARKER", "PROBE_CWD", "PROBE_SCRIPT", "PROBE_PYTHON"]
    assert "PROBE_MARKER: MISSING" in out
