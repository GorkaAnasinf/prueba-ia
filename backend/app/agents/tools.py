import logging
import re
import subprocess
import tempfile
import httpx
import yt_dlp
from langchain_core.tools import tool
from pathlib import Path
from datetime import datetime

from ..config import settings
from ..database import SessionLocal
from ..models import Task
from ..routers.rag import hybrid_search

logger = logging.getLogger(__name__)


@tool
def search_vault(query: str) -> str:
    """Busca información relevante en la base de conocimiento (vault de Obsidian)."""
    try:
        results = hybrid_search(query)
        if not results:
            return "No se encontró información relevante en el vault."
        return "\n\n---\n\n".join(
            f"[{r['file']}]\n{r['content']}" for r in results
        )
    except Exception as e:
        return f"Error en búsqueda: {e}"


@tool
def web_search(query: str) -> str:
    """Busca información actualizada en la web usando SearXNG."""
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{settings.searxng_url}/search",
                params={"q": query, "format": "json", "language": "es-ES"},
            )
            resp.raise_for_status()
        results = resp.json().get("results", [])[:5]
        if not results:
            return "No se encontraron resultados web."
        lines = []
        for r in results:
            title = r.get("title", "")
            content = r.get("content", "")
            url = r.get("url", "")
            lines.append(f"**{title}**\n{content}\n{url}")
        return "\n\n---\n\n".join(lines)
    except Exception as e:
        return f"Error en búsqueda web: {e}"


@tool
def create_task(title: str, description: str, responsible: str, due_date: str, project: str, source_file: str = "") -> str:
    """Crea una tarea en la base de datos y genera un archivo .md en el vault."""
    db = SessionLocal()
    try:
        existing = db.query(Task).filter(Task.title == title).first()
        if existing:
            return f"Tarea ya existe (omitida): '{title}'"
        task = Task(
            title=title,
            description=description,
            responsible=responsible,
            due_date=due_date,
            project=project,
            source_file=source_file,
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        push_ok = _write_task_md(task)
        suffix = "" if push_ok else " (⚠️ git push fallido)"
        return f"Tarea creada: '{title}'{suffix}"
    except Exception as e:
        db.rollback()
        return f"Error al crear tarea: {e}"
    finally:
        db.close()


@tool
def complete_task(title: str) -> str:
    """Marca una tarea como completada buscándola por título (búsqueda parcial)."""
    db = SessionLocal()
    try:
        task = db.query(Task).filter(Task.title.ilike(f"%{title}%")).first()
        if not task:
            return f"No se encontró tarea con título similar a: '{title}'"
        task.status = "done"
        db.commit()
        return f"Tarea marcada como completada: '{task.title}'"
    except Exception as e:
        db.rollback()
        return f"Error al completar tarea: {e}"
    finally:
        db.close()


@tool
def list_tasks(project: str = "", status: str = "") -> str:
    """Lista las tareas existentes, opcionalmente filtradas por proyecto o estado."""
    db = SessionLocal()
    try:
        q = db.query(Task)
        if project:
            q = q.filter(Task.project.ilike(f"%{project}%"))
        if status:
            q = q.filter(Task.status == status)
        tasks = q.order_by(Task.created_at.desc()).limit(30).all()
        if not tasks:
            return "No hay tareas."
        lines = [f"- [{t.status}] {t.title} | {t.responsible} | {t.due_date} | {t.project}" for t in tasks]
        return "\n".join(lines)
    except Exception as e:
        return f"Error al listar tareas: {e}"
    finally:
        db.close()


@tool
def transcribe_youtube(url: str) -> str:
    """Descarga un vídeo de YouTube, transcribe el audio con Whisper y guarda la transcripción en el vault."""
    with tempfile.TemporaryDirectory() as tmp:
        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": f"{tmp}/audio.%(ext)s",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "96",
            }],
            "quiet": True,
            "no_warnings": True,
        }
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "youtube-video")
            logger.info(f"yt-dlp descargado: {title}")
        except Exception as e:
            logger.error(f"yt-dlp error: {e}")
            return f"Error descargando vídeo: {e}"

        audio_path = Path(tmp) / "audio.mp3"
        if not audio_path.exists():
            logger.error(f"Audio no encontrado en {audio_path}")
            return "Error: no se pudo descargar el audio"
        audio_bytes = audio_path.read_bytes()
        logger.info(f"Audio descargado: {len(audio_bytes)} bytes")

    try:
        files = {"file": ("audio.mp3", audio_bytes, "audio/mpeg")}
        data = {"model": settings.whisper_model, "response_format": "text"}
        logger.info(f"Enviando a Speaches: {settings.speaches_url}")
        with httpx.Client(timeout=180) as client:
            resp = client.post(f"{settings.speaches_url}/v1/audio/transcriptions", files=files, data=data)
            resp.raise_for_status()
        transcript = resp.text.strip()
        logger.info(f"Transcripción OK: {len(transcript)} chars")
    except Exception as e:
        logger.error(f"Speaches error: {e}")
        return f"Error transcribiendo: {e}"

    vault = Path(settings.obsidian_vault_path)
    yt_dir = vault / "knowledge" / "youtube"
    yt_dir.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^\w\-]", "-", title[:50].lower())
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = yt_dir / f"{date_str}-{slug}.md"
    filepath.write_text(
        f"---\ntags: [youtube, transcripcion]\nfecha: {date_str}\nurl: {url}\n---\n\n# {title}\n\n{transcript}\n",
        encoding="utf-8",
    )
    _git_push_vault(f"obsidian-vault/knowledge/youtube/{filepath.name}", "youtube")
    return f"Transcripción guardada: {filepath.name}\n\n{transcript[:1000]}{'...' if len(transcript) > 1000 else ''}"


def save_doc_to_vault(title: str, content: str) -> bool:
    vault = Path(settings.obsidian_vault_path)
    knowledge_dir = vault / "knowledge" / "documents"
    knowledge_dir.mkdir(parents=True, exist_ok=True)

    slug = title[:50].lower().replace(" ", "-").replace("/", "-")
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = knowledge_dir / f"{date_str}-{slug}.md"

    full_content = f"""---
tags: [documento, generado]
fecha: {date_str}
---

{content}
"""
    filepath.write_text(full_content, encoding="utf-8")
    return _git_push_vault(f"knowledge/documents/{filepath.name}", "docs")


def _write_task_md(task: Task) -> bool:
    vault = Path(settings.obsidian_vault_path)
    projects_dir = vault / "projects"
    projects_dir.mkdir(exist_ok=True)

    slug = task.title[:40].lower().replace(" ", "-").replace("/", "-")
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    filepath = projects_dir / f"{date_str}-{slug}.md"

    content = f"""---
tags: [tarea, {task.status}]
proyecto: {task.project}
responsable: {task.responsible}
fecha_limite: {task.due_date}
estado: {task.status}
task_id: {task.id}
---

# {task.title}

## Descripción
{task.description}

## Detalles
- **Proyecto:** {task.project}
- **Responsable:** {task.responsible}
- **Fecha límite:** {task.due_date}
- **Estado:** {task.status}
- **Origen:** {task.source_file}

## Progreso

- [ ] Pendiente
"""
    filepath.write_text(content, encoding="utf-8")
    return _git_push_vault(f"obsidian-vault/projects/{filepath.name}", "tasks")


def _git_push_vault(relative_path: str, prefix: str = "vault") -> bool:
    repo = Path(settings.git_repo_path)
    try:
        subprocess.run(["git", "add", relative_path], cwd=repo, check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", f"{prefix}: {Path(relative_path).name}"],
            cwd=repo, capture_output=True,
        )
        if result.returncode != 0 and b"nothing to commit" not in result.stdout:
            logger.warning(f"Git commit failed: {result.stderr.decode()}")
            return False
        subprocess.run(["git", "push", "origin", "main"], cwd=repo, check=True, capture_output=True)
        logger.info(f"Auto-pushed: {relative_path}")
        return True
    except subprocess.CalledProcessError as e:
        logger.warning(f"Git push failed: {e.stderr.decode()}")
        return False
