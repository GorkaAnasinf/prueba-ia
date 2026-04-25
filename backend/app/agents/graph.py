from typing import TypedDict, Annotated, Literal
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, BaseMessage, AIMessage
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent

from ..config import settings
from .tools import search_vault, create_task, list_tasks


class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    agent_used: str


class RouteDecision(BaseModel):
    agent: Literal["research", "writer", "analyst", "task"]


SYSTEM_PROMPTS = {
    "research": (
        "Eres un agente de investigación. Busca información en el vault de conocimiento "
        "y responde con precisión basándote en los documentos encontrados. "
        "Cita siempre el archivo fuente."
    ),
    "writer": (
        "Eres un agente redactor. Generas documentos profesionales (propuestas, actas, correos, informes) "
        "basándote en la información del vault. Usa formato markdown estructurado."
    ),
    "analyst": (
        "Eres un agente analítico. Analiza múltiples proyectos, cruza información de diferentes fuentes "
        "y genera informes con conclusiones claras. Usa tablas y listas cuando sea útil."
    ),
    "task": (
        "Eres un agente de gestión de tareas. Analiza el contenido proporcionado, identifica acciones concretas "
        "y crea las tareas correspondientes con título, descripción, responsable, fecha límite y proyecto. "
        "Confirma cada tarea creada con sus detalles."
    ),
}

AGENT_TOOLS = {
    "research": [search_vault],
    "writer": [search_vault],
    "analyst": [search_vault, list_tasks],
    "task": [search_vault, create_task, list_tasks],
}

AGENT_MODELS = {
    "research": "chat",
    "writer": "chat",
    "analyst": "reasoning",
    "task": "reasoning",
}


def _get_llm(model: str) -> ChatOpenAI:
    return ChatOpenAI(
        model=model,
        base_url=f"{settings.litellm_base_url}/v1",
        api_key=settings.litellm_master_key,
        timeout=120,
    )


def router_node(state: AgentState) -> dict:
    llm = _get_llm("reasoning")
    structured = llm.with_structured_output(RouteDecision)
    last_msg = state["messages"][-1].content

    decision = structured.invoke([
        SystemMessage(content=(
            "Clasifica la consulta en uno de estos agentes:\n"
            "- research: preguntas sobre reuniones, acuerdos, información del vault\n"
            "- writer: redactar documentos, propuestas, actas, correos\n"
            "- analyst: análisis de proyectos, informes, comparativas, estado general\n"
            "- task: crear tareas, extraer acciones de reuniones, listar pendientes\n"
            "Responde solo con el nombre del agente."
        )),
        *state["messages"],
    ])
    return {"agent_used": decision.agent}


def make_agent_node(agent_name: str):
    def node(state: AgentState) -> dict:
        llm = _get_llm(AGENT_MODELS[agent_name])
        tools = AGENT_TOOLS[agent_name]
        system = SYSTEM_PROMPTS[agent_name]
        react_agent = create_react_agent(llm, tools)
        messages = [SystemMessage(content=system)] + list(state["messages"])
        result = react_agent.invoke({"messages": messages})
        ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        return {"messages": [ai_msgs[-1]], "agent_used": state.get("agent_used", agent_name)}
    return node


def build_graph():
    workflow = StateGraph(AgentState)

    workflow.add_node("router", router_node)
    for name in ["research", "writer", "analyst", "task"]:
        workflow.add_node(name, make_agent_node(name))

    workflow.add_edge(START, "router")
    workflow.add_conditional_edges(
        "router",
        lambda state: state["agent_used"],
        {"research": "research", "writer": "writer", "analyst": "analyst", "task": "task"},
    )
    for name in ["research", "writer", "analyst", "task"]:
        workflow.add_edge(name, END)

    return workflow.compile()


graph = build_graph()
