from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import httpx
import uuid
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, ScoredPoint

from ..auth import require_api_key
from ..config import settings

router = APIRouter(prefix="/rag", tags=["rag"])

VECTOR_SIZE = 768
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150


def _qdrant() -> QdrantClient:
    return QdrantClient(url=settings.qdrant_url)


def _ensure_collection(client: QdrantClient):
    names = [c.name for c in client.get_collections().collections]
    if settings.rag_collection not in names:
        client.create_collection(
            collection_name=settings.rag_collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


def _chunk(text: str) -> list[str]:
    chunks, start = [], 0
    while start < len(text):
        chunks.append(text[start : start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return [c for c in chunks if c.strip()]


def _embed(text: str) -> list[float]:
    with httpx.Client(timeout=60) as client:
        resp = client.post(
            f"{settings.ollama_base_url}/api/embeddings",
            json={"model": settings.embed_model, "prompt": text},
        )
        resp.raise_for_status()
    return resp.json()["embedding"]


class IngestResponse(BaseModel):
    files_processed: int
    chunks_indexed: int


class QueryRequest(BaseModel):
    query: str
    top_k: int = 5


class QueryResult(BaseModel):
    file: str
    content: str
    score: float


class QueryResponse(BaseModel):
    results: list[QueryResult]


@router.post("/ingest", response_model=IngestResponse)
def ingest(_: str = Depends(require_api_key)):
    vault = Path(settings.obsidian_vault_path)
    if not vault.exists():
        raise HTTPException(status_code=500, detail=f"Vault not found: {vault}")

    client = _qdrant()
    _ensure_collection(client)

    points: list[PointStruct] = []
    files_processed = 0

    for md_file in vault.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            rel_path = str(md_file.relative_to(vault))
            for i, chunk in enumerate(_chunk(content)):
                point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{rel_path}:{i}"))
                points.append(PointStruct(
                    id=point_id,
                    vector=_embed(chunk),
                    payload={"file": rel_path, "chunk_index": i, "content": chunk},
                ))
            files_processed += 1
        except Exception:
            continue

    if points:
        client.upsert(collection_name=settings.rag_collection, points=points)

    return IngestResponse(files_processed=files_processed, chunks_indexed=len(points))


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, _: str = Depends(require_api_key)):
    client = _qdrant()
    _ensure_collection(client)

    hits: list[ScoredPoint] = client.search(
        collection_name=settings.rag_collection,
        query_vector=_embed(req.query),
        limit=req.top_k,
    )

    return QueryResponse(results=[
        QueryResult(
            file=h.payload["file"],
            content=h.payload["content"],
            score=h.score,
        )
        for h in hits
    ])
