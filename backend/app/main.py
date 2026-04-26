import logging
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI
from .config import settings
from .database import engine
from .models import Base
from .routers import chat, conversations, rag, openai_compat, tasks, agent, channels
from .routers.rag import do_ingest
from .watcher import start_watcher

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        result = do_ingest()
        logger.info(f"Startup ingest: {result.files_processed} files, {result.chunks_indexed} chunks")
    except Exception as e:
        logger.warning(f"Startup ingest skipped: {e}")

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
app.include_router(channels.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.app_name}
