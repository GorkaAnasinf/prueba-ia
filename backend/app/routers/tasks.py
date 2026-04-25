from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from ..database import get_db
from ..models import Task
from ..auth import require_api_key

router = APIRouter(prefix="/tasks", tags=["tasks"])


class TaskResponse(BaseModel):
    id: str
    title: str
    description: str
    status: str
    responsible: str
    due_date: str
    project: str
    source_file: str
    created_at: str

    class Config:
        from_attributes = True


class TaskUpdate(BaseModel):
    status: str


@router.get("/", response_model=list[TaskResponse])
def list_tasks(
    project: str = "",
    status: str = "",
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    q = db.query(Task)
    if project:
        q = q.filter(Task.project.ilike(f"%{project}%"))
    if status:
        q = q.filter(Task.status == status)
    tasks = q.order_by(Task.created_at.desc()).limit(100).all()
    return [
        TaskResponse(
            id=t.id,
            title=t.title,
            description=t.description,
            status=t.status,
            responsible=t.responsible,
            due_date=t.due_date,
            project=t.project,
            source_file=t.source_file,
            created_at=t.created_at.isoformat(),
        )
        for t in tasks
    ]


@router.patch("/{task_id}", response_model=TaskResponse)
def update_task_status(
    task_id: str,
    update: TaskUpdate,
    db: Session = Depends(get_db),
    _: str = Depends(require_api_key),
):
    task = db.get(Task, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    task.status = update.status
    db.commit()
    db.refresh(task)
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        status=task.status,
        responsible=task.responsible,
        due_date=task.due_date,
        project=task.project,
        source_file=task.source_file,
        created_at=task.created_at.isoformat(),
    )
