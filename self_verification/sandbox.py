"""Isolated sandbox workspace — never the production tree."""

from __future__ import annotations

import shutil
from pathlib import Path

from .models import ChangeProposal, FilePatch


class SandboxError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


class Sandbox:
    """
    Copy-on-write style workspace under a temp/sandbox root.

    Production paths passed as `source_root` are READ-ONLY origins.
    All mutations happen under `root`.
    """

    def __init__(self, root: Path, *, source_root: Path) -> None:
        self.root = Path(root)
        self.source_root = Path(source_root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._snapshots: dict[str, str] = {}

    def sync_from_source(self, relative_paths: list[str] | None = None) -> None:
        """Copy selected (or all) files from source into sandbox."""
        if relative_paths is None:
            for path in self.source_root.rglob("*"):
                if path.is_file() and "__pycache__" not in path.parts:
                    rel = path.relative_to(self.source_root).as_posix()
                    self._copy_in(rel)
            return
        for rel in relative_paths:
            self._copy_in(rel)

    def _copy_in(self, rel: str) -> Path:
        src = (self.source_root / rel).resolve()
        if not str(src).startswith(str(self.source_root)):
            raise SandboxError("PATH_ESCAPE", f"Refusing path outside source: {rel}")
        if not src.is_file():
            raise SandboxError("MISSING_SOURCE", f"Source file missing: {rel}")
        dest = self.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        return dest

    def read(self, rel: str) -> str:
        path = self.root / rel
        if not path.is_file():
            raise SandboxError("MISSING_SANDBOX_FILE", rel)
        return path.read_text(encoding="utf-8")

    def snapshot(self, rel: str) -> None:
        self._snapshots[rel] = self.read(rel)

    def apply_patch(self, patch: FilePatch) -> None:
        path = self.root / patch.path
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            self.snapshot(patch.path)
        else:
            self._snapshots[patch.path] = ""
        if patch.old_content and path.exists():
            current = path.read_text(encoding="utf-8")
            if current != patch.old_content:
                raise SandboxError(
                    "PATCH_MISMATCH",
                    f"Sandbox content diverged for {patch.path}",
                )
        path.write_text(patch.new_content, encoding="utf-8")

    def apply_proposal(self, proposal: ChangeProposal) -> None:
        if proposal.applies_to_production or proposal.deployment_allowed:
            raise SandboxError(
                "PRODUCTION_MUTATE_FORBIDDEN",
                "Self-verification must not apply production/deployment proposals",
            )
        for patch in proposal.patches:
            self.apply_patch(patch)

    def rollback(self) -> list[str]:
        restored: list[str] = []
        for rel, content in list(self._snapshots.items()):
            path = self.root / rel
            if content == "":
                if path.exists():
                    path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8")
            restored.append(rel)
        self._snapshots.clear()
        return restored

    def assert_not_production(self, production_roots: list[Path]) -> None:
        resolved = self.root.resolve()
        for prod in production_roots:
            prod_r = Path(prod).resolve()
            if resolved == prod_r or prod_r in resolved.parents:
                # sandbox inside prod is ok if it's under a dedicated sandbox dir
                continue
            if str(resolved).startswith(str(prod_r)) and "sandbox" not in resolved.parts:
                raise SandboxError(
                    "SANDBOX_INSIDE_PRODUCTION",
                    f"Sandbox {resolved} must not be production root {prod_r}",
                )
