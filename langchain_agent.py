import os
import sqlite3
import time
from typing import List

from langchain_classic.agents.react.agent import create_react_agent
from langchain_classic.agents.agent import AgentExecutor
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import PromptTemplate
from langchain.tools import tool

from ddgs import DDGS
import trafilatura


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.0.242:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:1b-it-qat")


# -------------------------
# SIMPLE SQLITE CACHE
# -------------------------

CACHE_DB = os.getenv("AGENT_CACHE_DB", "agent_cache.db")

def init_cache():
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS cache (query TEXT PRIMARY KEY, answer TEXT, ts REAL)"
    )
    conn.commit()
    conn.close()

def cache_get(query: str):
    conn = sqlite3.connect(CACHE_DB)
    cur = conn.cursor()
    cur.execute("SELECT answer FROM cache WHERE query=?", (query,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None

def cache_set(query: str, answer: str):
    conn = sqlite3.connect(CACHE_DB)
    conn.execute(
        "INSERT OR REPLACE INTO cache (query, answer, ts) VALUES (?, ?, ?)",
        (query, answer, time.time()),
    )
    conn.commit()
    conn.close()

init_cache()


# -------------------------
# TOOLS (without @tool decorator)
# -------------------------

@tool
def web_search(query: str) -> str:
    """Search the web for current or factual information. Always include sources."""
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=3):
            results.append(
                f"- {r.get('title','')}: {r.get('body','')} [SOURCE: {r.get('href','')}]"
            )
    return "\n".join(results) or "No search results."


@tool
def scrape_page(url: str) -> str:
    """Scrape a webpage to extract detailed information. Preserve the source."""
    try:
        downloaded = trafilatura.fetch_url(url)
        text = trafilatura.extract(downloaded)
        return f"{(text or '')[:1500]}\n[SOURCE: {url}]"
    except Exception:
        return "Failed to scrape page."


# -------------------------
# QUERY ROUTER
# -------------------------


def classify_query(query: str) -> str:
    q = query.lower()
    if any(k in q for k in ["latest", "today", "news", "update", "score", "match"]):
        return "news"
    return "theory"


# -------------------------
# BUILD AGENT (ReAct agent for Ollama)
# -------------------------

def build_agent(mode: str):
    llm = ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.2 if mode == "theory" else 0.1,
    )
    tools = [web_search, scrape_page]

    template = """Answer the following questions as best you can. You have access to the following tools:

    {tools}

    Use the following format:

    Question: the input question you must answer
    Thought: you should always think about what to do
    Action: the action to take, can be one of [{tool_names}] or you can respond directly simple
    Action Input: the input to the action, MUST be valid JSON format like {{"a": 5, "b": 3}}
    Observation: the result of the action
    ... (this Thought/Action/Action Input/Observation can repeat N times)
    Thought: I now know the final answer
    Final Answer: the final answer to the original input question

    IMPORTANT: Always use JSON format for Action Input. For math operations, use {{"a": number1, "b": number2}}.

    Begin!

    Question: {input}
    Thought:{agent_scratchpad}"""

    prompt = PromptTemplate.from_template(template)

    agent = create_react_agent(
        llm=llm,
        tools=tools,
        prompt=prompt,
    )
    agent_executor = AgentExecutor(agent=agent, tools=tools, handle_parsing_errors=True)
    

    return agent_executor


_agents = {}

import asyncio

async def run_agent(query: str):
    cached = cache_get(query)
    if cached:
        return cached

    mode = classify_query(query)

    if mode not in _agents:
        _agents[mode] = build_agent(mode)

    agent = _agents[mode]

    # 🔑 run blocking agent in a thread
    answer = await asyncio.to_thread(
        agent.invoke,
        {"input": query}
    )

    # AgentExecutor returns dict
    if isinstance(answer, dict):
        answer = answer.get("output", "")

    cache_set(query, answer)
    return answer