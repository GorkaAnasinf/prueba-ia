from fastapi import FastAPI
from .config import settings
from .database import engine
from .models import Base
from .routers import chat, conversations, rag

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name, version="0.3.0")

app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(rag.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}
