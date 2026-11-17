"""Generated project file writer with per-agent ownership tracking (``forge_manifest.json``)."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, List, Optional

MANIFEST_NAME = "forge_manifest.json"
IGNORED_DIRS = {"node_modules", "dist", "__pycache__", ".pytest_cache", ".forge_runtime"}


class GeneratedProject:
    """A generated application rooted at ``root``. All writes are confined to that directory."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest: Dict[str, Dict] = {}
        manifest_path = self.root / MANIFEST_NAME
        if manifest_path.is_file():
            try:
                self.manifest = json.loads(manifest_path.read_text(encoding="utf-8")).get("files", {})
            except (OSError, ValueError):
                self.manifest = {}

    def _resolve(self, rel_path: str) -> Path:
        rel = PurePosixPath(rel_path.replace("\\", "/"))
        if rel.is_absolute() or ".." in rel.parts:
            raise ValueError(f"Refusing to write outside the project: {rel_path}")
        target = (self.root / Path(*rel.parts)).resolve()
        if self.root not in target.parents and target != self.root:
            raise ValueError(f"Refusing to write outside the project: {rel_path}")
        return target

    def write(self, rel_path: str, content: str, agent: str) -> Path:
        target = self._resolve(rel_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = content.replace("\r\n", "\n")
        if not data.endswith("\n"):
            data += "\n"
        target.write_text(data, encoding="utf-8", newline="\n")
        key = str(PurePosixPath(rel_path.replace("\\", "/")))
        self.manifest[key] = {
            "agent": agent,
            "sha256": hashlib.sha256(data.encode("utf-8")).hexdigest(),
            "bytes": len(data.encode("utf-8")),
        }
        return target

    def read(self, rel_path: str) -> str:
        return self._resolve(rel_path).read_text(encoding="utf-8")

    def exists(self, rel_path: str) -> bool:
        return self._resolve(rel_path).exists()

    def files_by_agent(self, agent: str) -> List[str]:
        return sorted(p for p, meta in self.manifest.items() if meta.get("agent") == agent)

    def save_manifest(self, extra: Optional[Dict] = None) -> Path:
        payload = {
            "generated_by": "FORGE AI",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "files": dict(sorted(self.manifest.items())),
        }
        if extra:
            payload.update(extra)
        path = self.root / MANIFEST_NAME
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path


def file_tree(root: Path) -> List[Dict]:
    """List files under root (excluding build/dependency folders) with sizes."""
    root = Path(root)
    items: List[Dict] = []
    if not root.is_dir():
        return items
    for path in sorted(root.rglob("*")):
        rel_parts = path.relative_to(root).parts
        if any(part in IGNORED_DIRS for part in rel_parts):
            continue
        if path.is_file():
            items.append({"path": "/".join(rel_parts), "bytes": path.stat().st_size})
    return items


def verify_manifest(root: Path) -> List[str]:
    """Return a list of problems (missing/modified files) comparing files on disk with the manifest."""
    root = Path(root)
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.is_file():
        return ["forge_manifest.json is missing"]
    try:
        files = json.loads(manifest_path.read_text(encoding="utf-8")).get("files", {})
    except ValueError:
        return ["forge_manifest.json is not valid JSON"]
    problems = []
    for rel, meta in files.items():
        path = root / Path(*PurePosixPath(rel).parts)
        if not path.is_file():
            problems.append(f"missing: {rel}")
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != meta.get("sha256"):
            problems.append(f"modified: {rel}")
    return problems
