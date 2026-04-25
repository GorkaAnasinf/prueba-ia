from langchain_core.tools import tool
from pathlib import Path
from datetime import datetime

from ..config import settings
from ..database import SessionLocal
from ..models import Task
from ..routers.rag import _embed, _qdrant, _ensure_collection


@tool
def search_vault(query: str) -> str:
    """Busca información relevante en la base de conocimiento (vault de Obsidian)."""
    try:
        client = _qdrant()
        _ensure_collection(client)
        hits = client.search(
            collection_name=settings.rag_collection,
            query_vector=_embed(query),
            limit=5,
        )
        if not hits:
            return "No se encontró información relevante."
        return "\n\n---\n\n".join(
            f"[{h.payload['file']}]\n{h.payload['content']}" for h in hits
        )
    except Exception as e:
        return f"Error en búsqueda: {e}"


@tool
def create_task(title: str, description: str, responsible: str, due_date: str, project: str, source_file: str = "") -> str:
    """Crea una tarea en la base de datos y genera un archivo .md en el vault."""
    db = SessionLocal()
    try:
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
        _write_task_md(task)
        return f"Tarea creada: '{title}' (ID: {task.id})"
    except Exception as e:
        db.rollback()
        return f"Error al crear tarea: {e}"
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


def _write_task_md(task: Task):
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
