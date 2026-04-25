"""
title: Agent Badge Filter
author: AI Platform
version: 1.0
description: Resalta el badge del agente usado al final de cada respuesta
"""

import re
from typing import Optional
from pydantic import BaseModel

AGENT_COLORS = {
    "research": "#4A90D9",
    "writer": "#7B68EE",
    "analyst": "#F5A623",
    "task": "#27AE60",
    "complete": "#2ECC71",
    "general": "#95A5A6",
}

BADGE_PATTERN = re.compile(r"\n\n---\n> 🤖 `agente: (\w+)`\s*$")


class Filter:
    class Valves(BaseModel):
        show_badge: bool = True

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        if not self.valves.show_badge:
            return body

        messages = body.get("messages", [])
        for msg in messages:
            if msg.get("role") != "assistant":
                continue
            content = msg.get("content", "")
            match = BADGE_PATTERN.search(content)
            if match:
                agent = match.group(1)
                color = AGENT_COLORS.get(agent, "#888")
                badge_html = (
                    f'\n\n<span style="'
                    f"font-size:0.72em;background:{color}22;color:{color};"
                    f"border:1px solid {color}66;border-radius:4px;"
                    f'padding:1px 7px;font-family:monospace">'
                    f"🤖 {agent}</span>"
                )
                msg["content"] = BADGE_PATTERN.sub(badge_html, content)
        return body
