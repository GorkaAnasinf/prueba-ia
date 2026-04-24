from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
import httpx

from ..database import get_db
from ..models import Conversation, Message
from ..auth import require_api_key
from ..config import settings

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    model: str = "chat"
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    message: str
    model: str


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
