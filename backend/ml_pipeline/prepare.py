from __future__ import annotations

import json
from pathlib import Path

from ml_pipeline.catalog import MODELS


def prepare_models(
    models_dir: Path, names: list[str], token: str | None = None
) -> dict:
    """Download once to persistent storage and lock each model to a Hub commit."""
    from huggingface_hub import HfApi, snapshot_download

    models_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = models_dir / "models.lock.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else {}
    )
    api = HfApi(token=token)
    for name in names:
        spec = MODELS[name]
        existing = manifest.get(name)
        if existing and existing.get("repo") == spec.repo and existing.get("sha"):
            sha = existing["sha"]
        else:
            sha = api.model_info(spec.repo, revision=spec.revision).sha
        if not sha:
            raise ValueError(f"cannot resolve immutable revision for {spec.repo}")
        snapshot_download(
            repo_id=spec.repo,
            revision=sha,
            token=token,
            local_dir=models_dir / name,
            allow_patterns=spec.allow_patterns,
        )
        manifest[name] = {"repo": spec.repo, "revision": spec.revision, "sha": sha}
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    return manifest
