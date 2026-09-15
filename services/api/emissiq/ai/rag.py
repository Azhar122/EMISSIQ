"""Lightweight retrieval over event evidence and maintenance history.

Embeddings are produced by a seeded hashing vectoriser rather than a downloaded
transformer: the corpus here is a few hundred short engineering sentences, the
demo must run offline, and a 256-dimension hashed bag-of-words retrieves them
perfectly well. Vectors are stored in pgvector so swapping in a real embedding
model later is a change of function, not of schema.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from ..db.models import EMBED_DIM, EventEvidence, MaintenanceRecord
from ..db.session import has_pgvector

_TOKEN = re.compile(r"[a-z0-9][a-z0-9\-]*")


def _tokens(s: str) -> list[str]:
    words = _TOKEN.findall(s.lower())
    # Character trigrams on tags like "c-03" so partial matches still retrieve.
    grams = [w[i : i + 3] for w in words if len(w) > 3 for i in range(len(w) - 2)]
    return words + grams


def embed(text_value: str) -> list[float]:
    vec = np.zeros(EMBED_DIM, dtype=np.float32)
    for tok in _tokens(text_value):
        h = int.from_bytes(hashlib.blake2b(tok.encode(), digest_size=8).digest(), "big")
        idx = h % EMBED_DIM
        sign = 1.0 if (h >> 8) % 2 else -1.0
        vec[idx] += sign
    norm = float(np.linalg.norm(vec))
    return (vec / norm).tolist() if norm > 0 else vec.tolist()


def _cosine(a: list[float], b: list[float]) -> float:
    va, vb = np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32)
    denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
    return float(va @ vb / denom) if denom else 0.0


def search_evidence(db: Session, query: str, event_id: str | None = None, k: int = 5) -> list[dict]:
    q = embed(query)
    stmt = select(EventEvidence)
    if event_id:
        stmt = stmt.where(EventEvidence.event_id == event_id)

    if has_pgvector():
        # Cosine distance operator; ordering happens in the database.
        rows = db.execute(
            stmt.order_by(EventEvidence.embedding.cosine_distance(q)).limit(k)
        ).scalars().all()
        return [{"summary": r.summary, "kind": r.kind, "detail": r.detail} for r in rows]

    rows = db.scalars(stmt).all()
    scored = [
        (_cosine(q, r.embedding), r) for r in rows if r.embedding is not None
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {"summary": r.summary, "kind": r.kind, "detail": r.detail} for _, r in scored[:k]
    ]


def search_maintenance(db: Session, query: str, k: int = 5) -> list[dict]:
    q = embed(query)
    stmt = select(MaintenanceRecord)
    if has_pgvector():
        rows = db.execute(
            stmt.order_by(MaintenanceRecord.embedding.cosine_distance(q)).limit(k)
        ).scalars().all()
    else:
        rows = db.scalars(stmt).all()
        scored = [(_cosine(q, r.embedding), r) for r in rows if r.embedding is not None]
        scored.sort(key=lambda pair: pair[0], reverse=True)
        rows = [r for _, r in scored[:k]]
    return [
        {
            "equipment_id": r.equipment_id,
            "task": r.task,
            "discipline": r.discipline,
            "notes": r.notes,
            "overdue": r.overdue,
            "performed_at": r.performed_at.isoformat() if r.performed_at else None,
            "due_at": r.due_at.isoformat() if r.due_at else None,
        }
        for r in rows
    ]
