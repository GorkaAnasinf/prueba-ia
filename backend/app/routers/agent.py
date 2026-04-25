from fastapi import APIRouter, Depends
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

from ..auth import require_api_key
from ..agents.graph import graph

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    message: str


class AgentResponse(BaseModel):
    agent_used: str
    message: str


@router.post("/chat", response_model=AgentResponse)
def agent_chat(req: AgentRequest, _: str = Depends(require_api_key)):
    result = graph.invoke({
        "messages": [HumanMessage(content=req.message)],
        "agent_used": "",
    })
    ai_messages = [m for m in result["messages"] if m.__class__.__name__ == "AIMessage"]
    return AgentResponse(
        agent_used=result.get("agent_used", "unknown"),
        message=ai_messages[-1].content if ai_messages else "Sin respuesta",
    )
