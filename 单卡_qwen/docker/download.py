"""Download the pinned snapshot, verify every weight against its published SHA256."""
import hashlib
import json
from pathlib import Path

from huggingface_hub import snapshot_download

root = Path("/work")
manifest = json.loads((root / "model-manifest.json").read_text())
dest = root / "models/nvidia-482ca0f"
snapshot_download(repo_id=manifest["repo"], revision=manifest["revision"], local_dir=dest)
index = json.loads((dest / "model.safetensors.index.json").read_text())
expected = {f["name"] for f in manifest["weights"]}
assert set(index["weight_map"].values()) == expected, "Unexpected/missing indexed shards"
records = []
for item in manifest["weights"]:
    path = dest / item["name"]
    assert path.stat().st_size == item["bytes"], f"Incorrect size: {path.name}"
    digest = hashlib.sha256()
    with path.open("rb") as src:
        for block in iter(lambda: src.read(8 * 1024 * 1024), b""):
            digest.update(block)
    assert digest.hexdigest() == item["sha256"], f"Incorrect SHA256: {path.name}"
    records.append({**item, "verified": True})
report = {"repo": manifest["repo"], "revision": manifest["revision"], "files": records}
(root / "reports/weights.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
