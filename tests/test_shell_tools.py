from __future__ import annotations

import subprocess

import pytest

import tools.shell_tools as shell_tools_module
from tools.shell_tools import ShellTools


def test_run_safe_command_rejects_shell_metacharacters() -> None:
    with pytest.raises(ValueError):
        ShellTools().run_safe_command("docker_logs", {"container": "bweg_app; docker rm -f x"})
