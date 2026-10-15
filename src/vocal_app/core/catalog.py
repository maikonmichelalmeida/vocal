"""Typed, local-only exercise catalogue extracted from the original style.js.

Resource paths come from the explicit manifest; titles are never used to guess
filenames. None in a note sequence denotes an unvoiced or unguided position.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sys


@dataclass(frozen=True)
class Exercise:
    id: int
    name: str
    category: str
    objective: str
    notes: str
    variation: str
    audio: str
    image: str | None
    bpm: int
    subdivision: int
    vocal_notes: tuple[str | None, ...]
    guide_notes: tuple[str | None, ...]
    breathing_seconds: int = 30
    durations_ms: tuple[int, ...] = ()

    @property
    def mode(self) -> str:
        return "breathing" if self.category == "Respiração" or not self.vocal_notes else "pitch"


@dataclass(frozen=True)
class Catalog:
    exercises: tuple[Exercise, ...]
    sessions: dict[str, tuple[int, ...]]
    session_focus: dict[str, str]
    assets_dir: Path
    source_revision: str

    @property
    def by_id(self) -> dict[int, Exercise]:
        return {exercise.id: exercise for exercise in self.exercises}

    def asset_path(self, relative: str) -> Path:
        path = (self.assets_dir / relative).resolve()
        if not path.is_relative_to(self.assets_dir.resolve()):
            raise ValueError(f"Recurso fora da pasta assets: {relative}")
        return path


def load_catalog(assets_dir: str | Path | None = None, *, verify_hashes: bool = False) -> Catalog:
    """Load all 39 exercises, checking required files (optionally their SHA-256).

    The default is the repository's assets directory; an explicit path supports
    packaged distributions without dependence on the current working directory.
    """
    if assets_dir is None:
        checkout_assets = Path(__file__).resolve().parents[3] / "assets"
        root = checkout_assets if (checkout_assets / "catalog.json").is_file() else Path(sys.prefix) / "share" / "vocal_app" / "assets"
    else:
        root = Path(assets_dir)
    root = root.resolve()
    data = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if data["schema_version"] != 1 or manifest["schema_version"] != 1:
        raise ValueError("Versão de catálogo não suportada")
    if data["source_revision"] != manifest["source_revision"]:
        raise ValueError("Catálogo e manifesto têm revisões diferentes")
    exercises = tuple(Exercise(**{**ex, "vocal_notes": tuple(ex["vocal_notes"]),
                                  "guide_notes": tuple(ex["guide_notes"])}) for ex in data["exercises"])
    catalog = Catalog(exercises, {key: tuple(ids) for key, ids in data["sessions"].items()},
                      data["session_focus"], root, data["source_revision"])
    if len(exercises) != 39 or set(catalog.by_id) != set(range(1, 40)):
        raise ValueError("O catálogo precisa conter exatamente os exercícios 1–39")
    if set(catalog.sessions) != set("ABCDEFGH") or set(catalog.session_focus) != set("ABCDEFGH"):
        raise ValueError("Sessões A–H ausentes ou inválidas")
    if any(not ids or any(ex_id not in catalog.by_id for ex_id in ids) for ids in catalog.sessions.values()):
        raise ValueError("Sessão contém exercício inexistente")
    expected = {(ex.id, kind): getattr(ex, kind) for ex in exercises for kind in ("audio", "image")
                if getattr(ex, kind) is not None}
    resources = manifest["resources"]
    actual = {(entry["exercise_id"], entry["kind"]): entry["path"] for entry in resources}
    if len(resources) != 75 or len(actual) != len(resources) or actual != expected:
        raise ValueError("Manifesto não corresponde aos 39 áudios e 36 imagens")
    for ex in exercises:
        if not 40 <= ex.bpm <= 180 or not 1 <= ex.subdivision <= 4:
            raise ValueError(f"Andamento inválido no exercício {ex.id}")
        if (ex.image is None) != (ex.id in (1, 2, 3)):
            raise ValueError(f"Imagem obrigatória ausente no exercício {ex.id}")
        if len(ex.vocal_notes) != len(ex.guide_notes):
            raise ValueError(f"Sequência e guia de comprimentos diferentes: {ex.id}")
    for entry in resources:
        file = catalog.asset_path(entry["path"])
        if not file.is_file():
            raise FileNotFoundError(f"Recurso do exercício {entry['exercise_id']} ausente: {file}")
        if file.stat().st_size != entry["bytes"]:
            raise ValueError(f"Tamanho do recurso alterado: {file}")
        if verify_hashes and hashlib.sha256(file.read_bytes()).hexdigest() != entry["sha256"]:
            raise ValueError(f"Integridade SHA-256 inválida: {file}")
    return catalog
