import asyncio
import json
import re
import time
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, BaseMessage
import httpx

from ..auth import require_bearer_key
from ..config import settings
from ..agents.graph import graph, router_node, AGENT_MODELS, _get_llm
from ..agents.tools import search_vault, web_search, list_tasks, transcribe_youtube
from ..cache import cache_get, cache_set
from ..memory import load_memory, save_memory

_YT_URL_RE = re.compile(r"https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+")

router = APIRouter(prefix="/v1", tags=["openai-compat"])

_STREAMABLE = {"research", "writer", "analyst", "general"}

_AGENT_BADGE = "\n\n---\n> 🤖 `agente: {agent}`"


def _convert_messages(messages: list[dict]) -> list[BaseMessage]:
    result = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "user":
            result.append(HumanMessage(content=content))
        elif role == "assistant":
            result.append(AIMessage(content=content))
        elif role == "system":
            result.append(SystemMessage(content=content))
    return result


def _sse_chunk(content: str, model: str, finish: bool = False) -> str:
    chunk = {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "delta": {} if finish else {"role": "assistant", "content": content},
            "finish_reason": "stop" if finish else None,
        }],
    }
    return f"data: {json.dumps(chunk)}\n\n"


def _wrap_openai(content: str, model: str, agent_used: str) -> dict:
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        "x_agent_used": agent_used,
    }


async def _build_context(agent: str, query: str) -> str:
    """Fetch vault + optional web context in parallel for research."""
    if agent == "research":
        vault_ctx, web_ctx = await asyncio.gather(
            asyncio.to_thread(search_vault.invoke, query),
            asyncio.to_thread(web_search.invoke, query),
        )
        has_vault = "No se encontró" not in vault_ctx and "Error" not in vault_ctx
        has_web = "No se encontraron" not in web_ctx and "Error" not in web_ctx
        if has_vault and has_web:
            return f"[VAULT]\n{vault_ctx}\n\n[WEB]\n{web_ctx}"
        if has_vault:
            return vault_ctx
        if has_web:
            return f"[WEB]\n{web_ctx}"
        return "No se encontró información relevante en el vault ni en la web."

    if agent in ("writer", "analyst"):
        context = await asyncio.to_thread(search_vault.invoke, query)
        if agent == "analyst":
            tasks_info = await asyncio.to_thread(list_tasks.invoke, {"project": "", "status": ""})
            context = f"{context}\n\nTAREAS EXISTENTES:\n{tasks_info}"
        return context

    return ""


def _system_prompt(agent: str, context: str, memory: str) -> str:
    mem = f"\n\n{memory}" if memory else ""
    if agent == "research":
        return (
            "Eres un agente de investigación. Usa el contexto proporcionado (vault interno y/o web). "
            "Indica la fuente entre corchetes: [archivo.md] para vault, [web] para web. "
            f"Si no hay contexto relevante, dilo claramente.{mem}\n\nCONTEXTO:\n{context}"
        )
    if agent == "writer":
        return (
            "Eres un agente redactor profesional. Genera documentos en markdown bien estructurados "
            f"basándote en el contexto del vault. Empieza directamente con el documento.{mem}\n\nCONTEXTO:\n{context}"
        )
    if agent == "analyst":
        return (
            "Eres un agente analítico. Analiza la información y genera informes con conclusiones claras. "
            f"Usa tablas y listas cuando sea útil.{mem}\n\nCONTEXTO:\n{context}"
        )
    return f"Eres un asistente útil y conciso.{mem}"


_AGENT_STEPS = {
    "research": ["Buscando en vault de Obsidian...", "Buscando en web (SearXNG)..."],
    "writer":   ["Buscando contexto en vault..."],
    "analyst":  ["Buscando en vault...", "Consultando tareas existentes..."],
    "general":  [],
}


async def _stream_youtube(url: str, messages: list[BaseMessage], model: str):
    yield _sse_chunk("<think>\nAgente seleccionado: **youtube**\n", model)
    yield _sse_chunk("Descargando audio del video de YouTube...\n", model)

    done_event = asyncio.Event()
    result_box: list[str] = []

    async def _run():
        r = await asyncio.to_thread(transcribe_youtube.invoke, {"url": url})
        result_box.append(r)
        done_event.set()

    task = asyncio.create_task(_run())

    elapsed = 0
    while not done_event.is_set():
        await asyncio.sleep(15)
        elapsed += 15
        if not done_event.is_set():
            yield _sse_chunk(f"Transcribiendo con Whisper... ({elapsed}s)\n", model)

    await task
    result = result_box[0] if result_box else "Error en transcripción"

    if result.startswith("Error"):
        yield _sse_chunk(f"{result}\n</think>\n\n", model)
        yield _sse_chunk(result, model)
        yield _sse_chunk("", model, finish=True)
        yield "data: [DONE]\n\n"
        return

    yield _sse_chunk("✓ Transcripción completada. Generando resumen...\n</think>\n\n", model)

    llm = _get_llm("chat")
    full_response = []
    async for chunk in llm.astream([
        SystemMessage(content=(
            "Eres un asistente que ayuda a entender el contenido de vídeos de YouTube. "
            "Resume el contenido y extrae los puntos clave de forma clara y estructurada en markdown."
        )),
        HumanMessage(content=f"Transcripción del vídeo:\n\n{result}"),
    ]):
        token = chunk.content
        if token:
            full_response.append(token)
            yield _sse_chunk(token, model)

    badge = _AGENT_BADGE.format(agent="youtube")
    yield _sse_chunk(badge, model)
    yield _sse_chunk("", model, finish=True)
    yield "data: [DONE]\n\n"


async def _stream_agent(agent: str, messages: list[BaseMessage], model: str):
    query = next((m.content for m in reversed(messages) if isinstance(m, HumanMessage)), "")
    memory = load_memory()

    # ── Thinking header ────────────────────────────────────────────────────────
    yield _sse_chunk(f"<think>\nAgente seleccionado: **{agent}**\n", model)
    if memory:
        yield _sse_chunk("Memoria de sesiones previas cargada.\n", model)

    cached = cache_get(query, agent)
    if cached:
        yield _sse_chunk("✓ Respuesta en caché (Redis)\n</think>\n\n", model)
        yield _sse_chunk(cached, model)
        yield _sse_chunk(_AGENT_BADGE.format(agent=agent), model)
        yield _sse_chunk("", model, finish=True)
        yield "data: [DONE]\n\n"
        return

    for step in _AGENT_STEPS.get(agent, []):
        yield _sse_chunk(f"{step}\n", model)

    context = await _build_context(agent, query)

    # Report what was found
    if agent == "research":
        has_vault = "[VAULT]" in context or ("No se encontró" not in context and "Error" not in context and "[WEB]" not in context)
        has_web = "[WEB]" in context
        if has_vault:
            yield _sse_chunk("✓ Contexto del vault encontrado.\n", model)
        if has_web:
            yield _sse_chunk("✓ Resultados web obtenidos.\n", model)
    elif agent in ("writer", "analyst"):
        yield _sse_chunk("✓ Contexto listo.\n", model)

    yield _sse_chunk("Generando respuesta...\n</think>\n\n", model)
    # ── End thinking ───────────────────────────────────────────────────────────

    system = _system_prompt(agent, context, memory)
    llm = _get_llm(AGENT_MODELS.get(agent, "chat"))

    full_response = []
    async for chunk in llm.astream([SystemMessage(content=system), *messages]):
        token = chunk.content
        if token:
            full_response.append(token)
            yield _sse_chunk(token, model)

    badge = _AGENT_BADGE.format(agent=agent)
    yield _sse_chunk(badge, model)
    yield _sse_chunk("", model, finish=True)
    yield "data: [DONE]\n\n"

    collected = "".join(full_response) + badge
    cache_set(query, agent, collected)
    await asyncio.to_thread(save_memory, messages, "".join(full_response))


@router.post("/chat/completions")
async def chat_completions(request: Request, _: str = Depends(require_bearer_key)):
    body = await request.json()
    raw_messages = body.get("messages", [])
    model = body.get("model", "chat")
    do_stream = body.get("stream", False)

    recent = raw_messages[-20:] if len(raw_messages) > 20 else raw_messages
    lc_messages = _convert_messages(recent)

    state = {"messages": lc_messages, "agent_used": ""}
    route_result = await asyncio.to_thread(router_node, state)
    agent = route_result["agent_used"]

    if agent == "youtube":
        query = next((m.content for m in reversed(lc_messages) if isinstance(m, HumanMessage)), "")
        match = _YT_URL_RE.search(query)
        url = match.group() if match else ""
        if do_stream:
            return StreamingResponse(
                _stream_youtube(url, lc_messages, model),
                media_type="text/event-stream",
            )
        result = await asyncio.to_thread(transcribe_youtube.invoke, {"url": url})
        return _wrap_openai(result, model, "youtube")

    if do_stream and agent in _STREAMABLE:
        return StreamingResponse(
            _stream_agent(agent, lc_messages, model),
            media_type="text/event-stream",
        )

    if agent in _STREAMABLE:
        query = next((m.content for m in reversed(lc_messages) if isinstance(m, HumanMessage)), "")
        memory = load_memory()
        cached = cache_get(query, agent)
        if cached:
            return _wrap_openai(cached, model, agent)

        context = await _build_context(agent, query)
        system = _system_prompt(agent, context, memory)
        llm = _get_llm(AGENT_MODELS.get(agent, "chat"))
        resp = await asyncio.to_thread(
            llm.invoke, [SystemMessage(content=system), *lc_messages]
        )
        badge = _AGENT_BADGE.format(agent=agent)
        content = resp.content + badge
        cache_set(query, agent, content)
        await asyncio.to_thread(save_memory, lc_messages, resp.content)
        return _wrap_openai(content, model, agent)

    # task / complete
    result = await asyncio.to_thread(
        graph.invoke,
        {"messages": lc_messages, "agent_used": agent},
    )
    ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
    agent_used = result.get("agent_used", agent)
    badge = _AGENT_BADGE.format(agent=agent_used)
    content = (ai_msgs[-1].content if ai_msgs else "Sin respuesta") + badge

    if do_stream:
        async def _wrap_stream():
            yield _sse_chunk(content, model)
            yield _sse_chunk("", model, finish=True)
            yield "data: [DONE]\n\n"
        return StreamingResponse(_wrap_stream(), media_type="text/event-stream")

    return _wrap_openai(content, model, agent_used)


@router.get("/models")
async def list_models(_: str = Depends(require_bearer_key)):
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{settings.litellm_base_url}/v1/models",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
        )
        resp.raise_for_status()
    return resp.json()
