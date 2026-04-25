import json
import re
from typing import TypedDict, Annotated, Literal
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages

from ..config import settings
from .tools import search_vault, web_search, create_task, complete_task, list_tasks, save_doc_to_vault

MAX_TASKS_PER_CALL = 10


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    agent_used: str


class RouteDecision(BaseModel):
    agent: Literal["research", "writer", "analyst", "task", "complete", "general"]


AGENT_MODELS = {
    "research": "chat",
    "writer": "chat",
    "analyst": "reasoning",
    "task": "reasoning",
    "complete": "chat",
    "general": "chat",
}


def _get_llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        base_url=f"{settings.litellm_base_url}/v1",
        api_key=settings.litellm_master_key,
        timeout=180,
    )


def _last_user_message(state: AgentState) -> str:
    for m in reversed(state["messages"]):
        if isinstance(m, HumanMessage):
            return m.content
    return ""


# ── Router ────────────────────────────────────────────────────────────────────

def router_node(state: AgentState) -> dict:
    llm = _get_llm("chat")
    resp = llm.invoke([
        SystemMessage(content=(
            "Eres un clasificador de intenciones. Analiza el historial de la conversación "
            "y clasifica el ÚLTIMO mensaje del usuario en exactamente una de estas palabras:\n"
            "research  — preguntas sobre información, reuniones, acuerdos, plazos, detalles del vault\n"
            "writer    — redactar documentos, propuestas, actas, correos, informes\n"
            "analyst   — análisis de proyectos, comparativas, estado general de múltiples proyectos\n"
            "task      — SOLO si pide EXPLÍCITAMENTE crear tareas nuevas\n"
            "complete  — marcar tareas como completadas, cambiar estado de tareas\n"
            "general   — conversación general, saludos, preguntas sin relación al vault\n\n"
            "IMPORTANTE: preguntas de seguimiento sobre tareas ya creadas son 'research', no 'task'.\n"
            "Responde SOLO con la palabra, sin explicación."
        )),
        *state["messages"],
    ])
    raw = resp.content.strip().lower()
    agent = raw if raw in ("research", "writer", "analyst", "task", "complete", "general") else "general"
    return {"agent_used": agent}


# ── Research agent ─────────────────────────────────────────────────────────────

def research_node(state: AgentState) -> dict:
    query = _last_user_message(state)
    vault_ctx = search_vault.invoke(query)
    web_ctx = web_search.invoke(query)

    has_vault = "No se encontró" not in vault_ctx and "Error" not in vault_ctx
    has_web = "No se encontraron" not in web_ctx and "Error" not in web_ctx

    if has_vault and has_web:
        context = f"[VAULT]\n{vault_ctx}\n\n[WEB]\n{web_ctx}"
    elif has_vault:
        context = vault_ctx
    elif has_web:
        context = f"[WEB]\n{web_ctx}"
    else:
        context = "No se encontró información relevante en el vault ni en la web."

    llm = _get_llm(AGENT_MODELS["research"])
    resp = llm.invoke([
        SystemMessage(content=(
            "Eres un agente de investigación. Usa el contexto proporcionado (vault interno y/o web). "
            "Indica la fuente entre corchetes: [archivo.md] para vault, [web] para resultados web. "
            "Si no hay contexto relevante, dilo claramente.\n\n"
            f"CONTEXTO:\n{context}"
        )),
        *state["messages"],
    ])
    return {"messages": [AIMessage(content=resp.content)], "agent_used": "research"}


# ── Writer agent ───────────────────────────────────────────────────────────────

def writer_node(state: AgentState) -> dict:
    query = _last_user_message(state)
    context = search_vault.invoke(query)
    llm = _get_llm(AGENT_MODELS["writer"])
    resp = llm.invoke([
        SystemMessage(content=(
            "Eres un agente redactor profesional. Genera documentos en markdown bien estructurados "
            "basándote en el contexto del vault. Empieza directamente con el documento.\n\n"
            f"CONTEXTO:\n{context}"
        )),
        HumanMessage(content=query),
    ])

    title = query[:60].strip()
    push_ok = save_doc_to_vault(title, resp.content)
    suffix = "\n\n---\n*Documento guardado en el vault.*" if push_ok else "\n\n---\n*⚠️ No se pudo guardar en el vault.*"

    return {"messages": [AIMessage(content=resp.content + suffix)], "agent_used": "writer"}


# ── Analyst agent ──────────────────────────────────────────────────────────────

def analyst_node(state: AgentState) -> dict:
    query = _last_user_message(state)
    context = search_vault.invoke(query)
    tasks_info = list_tasks.invoke({"project": "", "status": ""})
    llm = _get_llm(AGENT_MODELS["analyst"])
    resp = llm.invoke([
        SystemMessage(content=(
            "Eres un agente analítico. Analiza la información y genera informes con conclusiones claras. "
            "Usa tablas y listas cuando sea útil.\n\n"
            f"CONTEXTO DEL VAULT:\n{context}\n\n"
            f"TAREAS EXISTENTES:\n{tasks_info}"
        )),
        HumanMessage(content=query),
    ])
    return {"messages": [AIMessage(content=resp.content)], "agent_used": "analyst"}


# ── General agent ─────────────────────────────────────────────────────────────

def general_node(state: AgentState) -> dict:
    llm = _get_llm("chat")
    resp = llm.invoke([
        SystemMessage(content="Eres un asistente útil y conciso."),
        *state["messages"],
    ])
    return {"messages": [AIMessage(content=resp.content)], "agent_used": "general"}


# ── Complete agent ─────────────────────────────────────────────────────────────

def complete_node(state: AgentState) -> dict:
    query = _last_user_message(state)
    llm = _get_llm(AGENT_MODELS["complete"])

    resp = llm.invoke([
        SystemMessage(content=(
            "Extrae el título (o parte del título) de la tarea que el usuario quiere marcar como completada. "
            "Devuelve SOLO el título, sin explicación."
        )),
        HumanMessage(content=query),
    ])

    title = resp.content.strip()
    result = complete_task.invoke({"title": title})
    return {"messages": [AIMessage(content=result)], "agent_used": "complete"}


# ── Task agent ─────────────────────────────────────────────────────────────────

_TASK_SCHEMA = f"""
Devuelve un JSON con esta estructura (máximo {MAX_TASKS_PER_CALL} tareas):
[
  {{
    "title": "Título corto de la tarea",
    "description": "Descripción detallada",
    "responsible": "Nombre del responsable",
    "due_date": "YYYY-MM-DD o texto como '2025-11-15'",
    "project": "Nombre del proyecto",
    "source_file": "archivo origen si se conoce"
  }}
]
Devuelve SOLO el JSON, sin texto adicional, sin markdown.
"""


def _extract_json(text: str) -> list:
    text = text.strip()
    match = re.search(r'\[.*\]', text, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(text)


def task_node(state: AgentState) -> dict:
    query = _last_user_message(state)
    context = search_vault.invoke(query)
    llm = _get_llm(AGENT_MODELS["task"])

    resp = llm.invoke([
        SystemMessage(content=(
            f"Eres un agente de gestión de tareas. Extrae las acciones pendientes del contexto. "
            f"Máximo {MAX_TASKS_PER_CALL} tareas. Prioriza las más importantes.\n\n"
            f"CONTEXTO:\n{context}\n\n"
            f"{_TASK_SCHEMA}"
        )),
        HumanMessage(content=query),
    ])

    created, skipped, errors = [], [], []
    try:
        tasks_data = _extract_json(resp.content)[:MAX_TASKS_PER_CALL]
        for t in tasks_data:
            result = create_task.invoke(t)
            if "ya existe" in result:
                skipped.append(f"↩ {t['title']}")
            elif "Error" in result:
                errors.append(f"✗ {t['title']}: {result}")
            else:
                created.append(f"✓ {t['title']}")
    except Exception as e:
        errors.append(f"Error parseando tareas: {e}")

    parts = []
    if created:
        parts.append(f"Tareas creadas ({len(created)}):\n" + "\n".join(created))
    if skipped:
        parts.append(f"Ya existían ({len(skipped)}):\n" + "\n".join(skipped))
    if errors:
        parts.append(f"Errores:\n" + "\n".join(errors))

    summary = "\n\n".join(parts) if parts else "No se encontraron tareas que crear."
    return {"messages": [AIMessage(content=summary)], "agent_used": "task"}


# ── Graph ──────────────────────────────────────────────────────────────────────

def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    workflow.add_node("research", research_node)
    workflow.add_node("writer", writer_node)
    workflow.add_node("analyst", analyst_node)
    workflow.add_node("task", task_node)
    workflow.add_node("complete", complete_node)
    workflow.add_node("general", general_node)

    workflow.add_edge(START, "router")
    workflow.add_conditional_edges(
        "router",
        lambda state: state["agent_used"],
        {
            "research": "research",
            "writer": "writer",
            "analyst": "analyst",
            "task": "task",
            "complete": "complete",
            "general": "general",
        },
    )
    for name in ["research", "writer", "analyst", "task", "complete", "general"]:
        workflow.add_edge(name, END)

    return workflow.compile()


graph = build_graph()
