import re
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
import httpx
import uuid
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, ScoredPoint
from rank_bm25 import BM25Okapi

from ..auth import require_api_key
from ..config import settings

router = APIRouter(prefix="/rag", tags=["rag"])

VECTOR_SIZE = 768
CHUNK_SIZE = 1200
MIN_SCORE = 0.45
BM25_TOP_K = 20
HYBRID_TOP_K = 5
BM25_WEIGHT = 0.3
SEMANTIC_WEIGHT = 0.7


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
    sections = re.split(r'\n(?=#{1,3} )', text)
    chunks = []
    for section in sections:
        if len(section) <= CHUNK_SIZE:
            if section.strip():
                chunks.append(section.strip())
        else:
            paragraphs = section.split('\n\n')
            current = ""
            for para in paragraphs:
                if len(current) + len(para) + 2 <= CHUNK_SIZE:
                    current = (current + "\n\n" + para).strip()
                else:
                    if current:
                        chunks.append(current)
                    current = para.strip()
            if current:
                chunks.append(current)
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


def _is_excluded(path: Path, vault: Path) -> bool:
    rel = path.relative_to(vault)
    return rel.parts[0].startswith("_")


def do_ingest() -> IngestResponse:
    vault = Path(settings.obsidian_vault_path)
    if not vault.exists():
        raise FileNotFoundError(f"Vault not found: {vault}")

    client = _qdrant()
    _ensure_collection(client)

    points: list[PointStruct] = []
    files_processed = 0

    for md_file in vault.rglob("*.md"):
        if _is_excluded(md_file, vault):
            continue
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


def hybrid_search(query: str, top_k: int = HYBRID_TOP_K) -> list[dict]:
    """Combina búsqueda semántica (Qdrant) con BM25 para resultados más precisos."""
    client = _qdrant()
    _ensure_collection(client)

    # Semantic search — fetch more candidates for re-ranking
    hits = client.search(
        collection_name=settings.rag_collection,
        query_vector=_embed(query),
        limit=BM25_TOP_K,
        score_threshold=MIN_SCORE,
    )
    if not hits:
        return []

    docs = [h.payload["content"] for h in hits]
    files = [h.payload["file"] for h in hits]
    semantic_scores = [h.score for h in hits]

    # BM25 over the candidate set
    tokenized = [d.lower().split() for d in docs]
    bm25 = BM25Okapi(tokenized)
    bm25_scores = bm25.get_scores(query.lower().split())

    # Normalize each score array to [0, 1]
    def _norm(arr):
        mn, mx = min(arr), max(arr)
        if mx == mn:
            return [1.0] * len(arr)
        return [(v - mn) / (mx - mn) for v in arr]

    sem_n = _norm(semantic_scores)
    bm25_n = _norm(list(bm25_scores))

    combined = [
        SEMANTIC_WEIGHT * s + BM25_WEIGHT * b
        for s, b in zip(sem_n, bm25_n)
    ]

    ranked = sorted(
        zip(combined, docs, files),
        key=lambda x: x[0],
        reverse=True,
    )[:top_k]

    return [{"score": s, "content": c, "file": f} for s, c, f in ranked]


@router.post("/ingest", response_model=IngestResponse)
def ingest(_: str = Depends(require_api_key)):
    try:
        return do_ingest()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reindex", response_model=IngestResponse)
def reindex(_: str = Depends(require_api_key)):
    try:
        client = _qdrant()
        client.delete_collection(settings.rag_collection)
        return do_ingest()
    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query", response_model=QueryResponse)
def query(req: QueryRequest, _: str = Depends(require_api_key)):
    client = _qdrant()
    _ensure_collection(client)

    hits: list[ScoredPoint] = client.search(
        collection_name=settings.rag_collection,
        query_vector=_embed(req.query),
        limit=req.top_k,
        score_threshold=MIN_SCORE,
    )

    return QueryResponse(results=[
        QueryResult(
            file=h.payload["file"],
            content=h.payload["content"],
            score=h.score,
        )
        for h in hits
    ])
