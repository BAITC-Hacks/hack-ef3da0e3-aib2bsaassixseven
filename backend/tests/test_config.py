from pathlib import Path

import pytest

from app.core.config import Settings


def test_data_root_has_local_default_and_environment_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # BaseSettings still provides the production DATA_ROOT override while a
    # source checkout starts safely without an extra environment variable.
    monkeypatch.delenv("DATA_ROOT", raising=False)
    assert Settings(_env_file=None).data_root == Path("data")
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    assert Settings(_env_file=None).data_root == tmp_path
