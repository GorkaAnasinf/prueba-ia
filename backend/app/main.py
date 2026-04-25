from contextlib import asynccontextmanager
from fastapi import FastAPI
from .config import settings
from .database import engine
from .models import Base
from .routers import chat, conversations, rag, openai_compat, tasks, agent
from .watcher import start_watcher

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    observer = start_watcher()
    yield
    if observer:
        observer.stop()
        observer.join()


app = FastAPI(title=settings.app_name, version="0.6.0", lifespan=lifespan)

app.include_router(chat.router)
app.include_router(conversations.router)
app.include_router(rag.router)
app.include_router(openai_compat.router)
app.include_router(tasks.router)
app.include_router(agent.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}
