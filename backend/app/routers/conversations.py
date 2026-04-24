from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Conversation
from ..auth import require_api_key

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("/")
def list_conversations(db: Session = Depends(get_db), _: str = Depends(require_api_key)):
    convs = db.query(Conversation).order_by(Conversation.created_at.desc()).limit(50).all()
    return [
        {"id": c.id, "model": c.model, "title": c.title, "created_at": c.created_at}
        for c in convs
    ]


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str, db: Session = Depends(get_db), _: str = Depends(require_api_key)):
    conv = db.get(Conversation, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "id": conv.id,
        "model": conv.model,
        "title": conv.title,
        "created_at": conv.created_at,
        "messages": [
            {"role": m.role, "content": m.content, "created_at": m.created_at}
            for m in conv.messages
        ],
    }
