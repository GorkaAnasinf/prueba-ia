import re
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
CHUNK_SIZE = 1200
MIN_SCORE = 0.45


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


@router.post("/ingest", response_model=IngestResponse)
def ingest(_: str = Depends(require_api_key)):
    try:
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
