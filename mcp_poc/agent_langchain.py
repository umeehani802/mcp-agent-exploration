"""LangChain agent that uses MCP tools.

    LangChain Agent -> MCP Client (ClientSession) -> MCP Server -> Tool -> SQLite/Files -> Result -> Agent

Steps this file makes explicit:
  1. open_session()          -> connect + handshake with the MCP server
  2. load_mcp_tools(session) -> TOOL DISCOVERY: tools/list converted into LangChain tools
  3. create_agent(llm, tools)-> the LLM now *sees* each tool's name/description/JSON-schema
  4. agent.ainvoke(...)      -> the LLM SELECTS a tool, LangChain INVOKES it (tools/call over MCP),
                                the RESULT returns as a ToolMessage, and the LLM decides the next step.

Run:  python -m mcp_poc.agent_langchain "How many units of LAP-001 are in stock and what is that worth in PKR?"
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

from langchain_mcp_adapters.tools import load_mcp_tools

from .client import open_session

try:  # optional .env support
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

SYSTEM_PROMPT = (
    "You are a careful business assistant. Use the provided tools to answer; never guess inventory data "
    "or arithmetic. If a tool returns an error, read it, fix your arguments and retry once. "
    "Give a short final answer."
)


def build_llm():
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    model = os.getenv("LLM_MODEL")
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model or "claude-sonnet-5-5", temperature=0)
    if provider == "openai":
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model or "gpt-4o-mini", temperature=0)
    if provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=model or "llama3.1", temperature=0)
    raise SystemExit(f"Unknown LLM_PROVIDER '{provider}'. Use anthropic, openai or ollama.")


def build_agent(llm, tools):
    try:  # LangChain 1.x
        from langchain.agents import create_agent

        return create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)
    except ImportError:  # LangChain 0.3.x / LangGraph prebuilt
        from langgraph.prebuilt import create_react_agent

        return create_react_agent(llm, tools, prompt=SYSTEM_PROMPT)


def _as_text(content) -> str:
    if isinstance(content, str):
        return content
    return " ".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in content)


def print_trace(messages) -> None:
    """Show the agent loop: model decision -> tool call -> tool result -> ... -> final answer."""
    for m in messages:
        kind = m.__class__.__name__
        if kind == "HumanMessage":
            print(f"\n[USER]       {_as_text(m.content)}")
        elif kind == "AIMessage":
            for call in getattr(m, "tool_calls", []) or []:
                print(f"[AGENT]      selects tool  {call['name']}  args={call['args']}")
            text = _as_text(m.content).strip()
            if text:
                print(f"[AGENT]      {text}")
        elif kind == "ToolMessage":
            print(f"[MCP RESULT] {_as_text(m.content)[:400]}")


async def run(question: str, url: str | None) -> None:
    async with open_session(url) as session:
        tools = await load_mcp_tools(session)  # TOOL DISCOVERY
        print("Discovered MCP tools:", ", ".join(t.name for t in tools))
        agent = build_agent(build_llm(), tools)
        result = await agent.ainvoke({"messages": [("user", question)]})
        print_trace(result["messages"])
        print("\nFINAL ANSWER:", _as_text(result["messages"][-1].content))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LangChain agent using MCP tools")
    ap.add_argument("question", nargs="?", default="How many units of LAP-001 are in stock, and what is the total stock value in PKR?")
    ap.add_argument("--url", default=None, help="Connect to a running Streamable HTTP MCP server instead of spawning one")
    args = ap.parse_args()
    try:
        asyncio.run(run(args.question, args.url))
    except KeyboardInterrupt:
        sys.exit(130)
