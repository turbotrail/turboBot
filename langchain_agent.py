import os
import sqlite3
import time
from typing import List

try:
    # Newer LangChain versions
    from langchain.agents.agent import AgentExecutor
except ImportError:
    # Older LangChain fallback
    from langchain.agents import AgentExecutor
from langchain.agents.react.agent import create_react_agent
from langchain_community.chat_models import ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain.tools import Tool

from ddgs import DDGS
import trafilatura


OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://192.168.0.242:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma3:4b")


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

def web_search(query: str) -> str:
    """Search the web for current or factual information. Always include sources."""
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=6):
            results.append(
                f"- {r.get('title','')}: {r.get('body','')} [SOURCE: {r.get('href','')}]"
            )
    return "\n".join(results) or "No search results."


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

    tools = []
    if mode == "news":
        tools = [
            Tool(
                name="web_search",
                func=web_search,
                description="Search the web for recent or factual information.",
            ),
            Tool(
                name="scrape_page",
                func=scrape_page,
                description="Scrape a webpage for more detail.",
            ),
        ]

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                f"You are a {mode} research assistant.\n"
                "- Decide when to use tools\n"
                "- Cite sources using [SOURCE: url]\n"
                "- Never invent facts\n"
                "- If unsure, say so\n"
                "- Keep answers under 120 words",
            ),
            ("human", "{input}"),
            ("assistant", "{agent_scratchpad}"),
        ]
    )

    agent = create_react_agent(
        llm=llm,
        tools=tools,
        prompt=prompt,
    )

    return AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=False,
        max_iterations=5,
    )


_agents = {}

async def run_agent(query: str):
    cached = cache_get(query)
    if cached:
        return cached

    mode = classify_query(query)

    if mode not in _agents:
        _agents[mode] = build_agent(mode)

    agent = _agents[mode]

    answer = await agent.arun(query)

    cache_set(query, answer)
    return answer