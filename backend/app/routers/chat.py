from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import httpx

from ..database import get_db
from ..models import Conversation, Message
from ..auth import require_api_key
from ..config import settings
from .rag import _qdrant, _embed, _ensure_collection

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    model: str = "chat"
    conversation_id: str | None = None
    use_rag: bool = False


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    model: str


def _rag_context(query: str) -> str:
    try:
        client = _qdrant()
        _ensure_collection(client)
        hits = client.search(
            collection_name=settings.rag_collection,
            query_vector=_embed(query),
            limit=3,
        )
        if not hits:
            return ""
        chunks = "\n\n---\n\n".join(
            f"[{h.payload['file']}]\n{h.payload['content']}" for h in hits
        )
        return f"Contexto relevante de la base de conocimiento:\n\n{chunks}"
    except Exception:
        return ""


@router.post("/", response_model=ChatResponse)
def chat(req: ChatRequest, db: Session = Depends(get_db), _: str = Depends(require_api_key)):
    if req.conversation_id:
        conv = db.get(Conversation, req.conversation_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
    else:
        conv = Conversation(model=req.model)
        db.add(conv)
        db.flush()

    history = [{"role": m.role, "content": m.content} for m in conv.messages]

    if req.use_rag:
        context = _rag_context(req.message)
        if context:
            history.insert(0, {"role": "system", "content": context})

    history.append({"role": "user", "content": req.message})

    with httpx.Client(timeout=120) as client:
        resp = client.post(
            f"{settings.litellm_base_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json={"model": req.model, "messages": history},
        )
        resp.raise_for_status()

    assistant_content = resp.json()["choices"][0]["message"]["content"]

    db.add(Message(conversation_id=conv.id, role="user", content=req.message))
    db.add(Message(conversation_id=conv.id, role="assistant", content=assistant_content))
    db.commit()

    return ChatResponse(conversation_id=conv.id, message=assistant_content, model=req.model)
