from __future__ import annotations

from pathlib import Path

from security.policy import CommandPolicy


def test_policy_allows_safe_action(tmp_path: Path) -> None:
    allowed = tmp_path / "workspace"
    allowed.mkdir()
    policy = CommandPolicy(
        allowed_dirs=[allowed],
        allowed_apps={"notepad": "C:\\Windows\\System32\\notepad.exe"},
        allowed_network_hosts=["google.com"],
    )
    decision = policy.evaluate("find_file_by_name", {"name": "note.txt"})
    assert decision.allowed is True
    assert decision.requires_confirmation is False


def test_policy_blocks_blacklisted_pattern(tmp_path: Path) -> None:
    allowed = tmp_path / "workspace"
    allowed.mkdir()
    policy = CommandPolicy(
        allowed_dirs=[allowed],
        allowed_apps={},
        allowed_network_hosts=[],
    )
    decision = policy.evaluate("find_file_by_name", {"name": "a; rm -rf /"})
    assert decision.allowed is False
    assert "Blocked" in decision.reason


def test_policy_requires_confirmation_for_delete(tmp_path: Path) -> None:
    allowed = tmp_path / "workspace"
    allowed.mkdir()
    target = allowed / "x.txt"
    target.write_text("x", encoding="utf-8")

    policy = CommandPolicy(
        allowed_dirs=[allowed],
        allowed_apps={},
        allowed_network_hosts=[],
    )
    decision = policy.evaluate("delete_file", {"path": str(target)})
    assert decision.allowed is True
    assert decision.requires_confirmation is True


def test_policy_blocks_path_outside_allowlist(tmp_path: Path) -> None:
    allowed = tmp_path / "workspace"
    outside = tmp_path / "outside"
    allowed.mkdir()
    outside.mkdir()

    policy = CommandPolicy(
        allowed_dirs=[allowed],
        allowed_apps={},
        allowed_network_hosts=[],
    )
    decision = policy.evaluate("delete_file", {"path": str(outside / "a.txt")})
    assert decision.allowed is False
    assert "outside allowed directories" in decision.reason.lower()


def test_policy_blocks_unlisted_host(tmp_path: Path) -> None:
    allowed = tmp_path / "workspace"
    allowed.mkdir()
    policy = CommandPolicy(
        allowed_dirs=[allowed],
        allowed_apps={},
        allowed_network_hosts=["google.com"],
    )
    decision = policy.evaluate("ping_host", {"host": "example.com"})
    assert decision.allowed is False
