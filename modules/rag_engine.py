"""
Hybrid RAG Engine — Answers from *both* Vector DB and SQL DB.
=============================================================

Flow:
  1. Classify user intent → "data_query" | "knowledge_query" | "hybrid"
  2. Route to the appropriate retriever(s):
       • data_query      → SQL Agent  (structured price / rainfall / production data)
       • knowledge_query → ChromaDB   (uploaded documents)
       • hybrid          → both, merged context
  3. Feed retrieved context + question to the LLM for final answer.
"""

from __future__ import annotations

from typing import Any, Generator, Optional, List, Dict


# ═══════════════════════════════════════════════════════════════════════
#  Intent classification
# ═══════════════════════════════════════════════════════════════════════

_CLASSIFIER_PROMPT = """You are an intent classifier for a Cardamom Business application.
Given the user's question, classify it into ONE of these categories:

- "data_query"      : The question is about cardamom prices, quantities, dates, rainfall, 
                       production numbers, or any structured/numerical data that can be 
                       answered from a SQL database.
- "knowledge_query" : The question is about general knowledge, uploaded documents, reports,
                       articles, or information that would be found in text documents.
- "hybrid"          : The question requires BOTH structured data AND document knowledge.

Reply with ONLY the category name, nothing else."""


def classify_intent(question: str) -> str:
    """Return one of: data_query, knowledge_query, hybrid."""
    from modules.llm_provider import chat

    try:
        resp = chat(
            messages=[
                {"role": "system", "content": _CLASSIFIER_PROMPT},
                {"role": "user", "content": question},
            ],
            temperature=0.0,
            max_tokens=20,
        )
        intent = resp.choices[0].message.content.strip().lower().strip('"\'')
        if intent in ("data_query", "knowledge_query", "hybrid"):
            return intent
        return "hybrid"  # default to hybrid if unsure
    except Exception:
        return "hybrid"


# ═══════════════════════════════════════════════════════════════════════
#  Context retrieval
# ═══════════════════════════════════════════════════════════════════════

def _retrieve_sql_context(question: str) -> Dict[str, Any]:
    """Run the SQL agent and return context dict."""
    from modules.sql_agent import ask_sql

    try:
        result = ask_sql(question)
        return {
            "type": "sql",
            "context": result.get("context_text", "No SQL results."),
            "sql": result.get("sql", ""),
            "dataframe": result.get("result", {}).get("dataframe"),
            "success": result.get("result", {}).get("success", False),
        }
    except Exception as exc:
        return {
            "type": "sql",
            "context": f"SQL retrieval failed: {exc}",
            "sql": "",
            "dataframe": None,
            "success": False,
        }


def _retrieve_vector_context(question: str, n_results: int = 5) -> Dict[str, Any]:
    """Search ChromaDB and return context dict."""
    from modules.doc_processor import search_similar

    try:
        hits = search_similar(question, n_results=n_results)
        if not hits:
            return {
                "type": "vector",
                "context": "No relevant documents found in the knowledge base.",
                "sources": [],
                "success": False,
            }

        # Build context text with source citations
        context_parts = []
        sources = set()
        for i, hit in enumerate(hits, 1):
            context_parts.append(
                f"[Source {i}: {hit['source']}] (relevance: {hit['score']:.2f})\n"
                f"{hit['text']}"
            )
            sources.add(hit["source"])

        return {
            "type": "vector",
            "context": "\n\n---\n\n".join(context_parts),
            "sources": list(sources),
            "success": True,
        }
    except Exception as exc:
        return {
            "type": "vector",
            "context": f"Vector search failed: {exc}",
            "sources": [],
            "success": False,
        }


# ═══════════════════════════════════════════════════════════════════════
#  Answer generation
# ═══════════════════════════════════════════════════════════════════════

_SYSTEM_PROMPT = """You are an expert AI assistant for the Cardamom Business.
You help users understand cardamom market prices, production data, rainfall impacts,
and any information from uploaded documents about the cardamom industry.

When answering:
- Use the provided context to give accurate, data-backed answers.
- If SQL data is provided, reference specific numbers and dates.
- If document context is provided, cite the source.
- If you don't have enough information, say so honestly.
- Be concise but thorough.
- Format numbers clearly (e.g., Rs. 2,500.00/Kg).
- Use markdown formatting for readability."""


def ask(
    question: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    force_intent: Optional[str] = None,
) -> Dict[str, Any]:
    """Full RAG pipeline: classify → retrieve → generate.

    Args:
        question: The user's question.
        chat_history: Previous messages in the conversation.
        force_intent: Override intent classification (for testing).

    Returns:
        Dict with: answer, intent, sources, sql, dataframe.
    """
    from modules.llm_provider import chat as llm_chat

    # 1. Classify intent
    intent = force_intent or classify_intent(question)

    # 2. Retrieve context
    sql_ctx = None
    vec_ctx = None

    if intent in ("data_query", "hybrid"):
        sql_ctx = _retrieve_sql_context(question)

    if intent in ("knowledge_query", "hybrid"):
        vec_ctx = _retrieve_vector_context(question)

    # 3. Build context block
    context_parts = []
    if sql_ctx and sql_ctx.get("context"):
        context_parts.append(
            f"=== DATABASE RESULTS ===\n{sql_ctx['context']}"
        )
    if vec_ctx and vec_ctx.get("context"):
        context_parts.append(
            f"=== DOCUMENT KNOWLEDGE ===\n{vec_ctx['context']}"
        )

    context_text = "\n\n".join(context_parts) if context_parts else "No context available."

    # 4. Build messages
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]

    # Include chat history if provided
    if chat_history:
        messages.extend(chat_history[-10:])  # Keep last 10 messages for context

    messages.append({
        "role": "user",
        "content": (
            f"Context:\n{context_text}\n\n"
            f"Question: {question}\n\n"
            "Please answer based on the context provided above."
        ),
    })

    # 5. Generate answer
    try:
        resp = llm_chat(messages, temperature=0.3, max_tokens=4096)
        answer = resp.choices[0].message.content
    except Exception as exc:
        answer = f"I encountered an error generating a response: {exc}"

    # 6. Compile sources
    sources = []
    if sql_ctx and sql_ctx.get("success"):
        sources.append({"type": "SQL Database", "detail": sql_ctx.get("sql", "")})
    if vec_ctx and vec_ctx.get("sources"):
        for src in vec_ctx["sources"]:
            sources.append({"type": "Document", "detail": src})

    return {
        "answer": answer,
        "intent": intent,
        "sources": sources,
        "sql": sql_ctx.get("sql") if sql_ctx else None,
        "dataframe": sql_ctx.get("dataframe") if sql_ctx else None,
    }


def ask_stream(
    question: str,
    chat_history: Optional[List[Dict[str, str]]] = None,
    force_intent: Optional[str] = None,
) -> Generator[Dict[str, Any], None, None]:
    """Streaming version of ask() — yields partial answer chunks.

    Yields dicts with:
      - type: "meta" | "token" | "done"
      - For "meta": intent, sources, sql, dataframe
      - For "token": text (partial answer chunk)
      - For "done": full_answer
    """
    from modules.llm_provider import chat_stream as llm_stream

    # 1. Classify intent
    intent = force_intent or classify_intent(question)

    # 2. Retrieve context
    sql_ctx = None
    vec_ctx = None

    if intent in ("data_query", "hybrid"):
        sql_ctx = _retrieve_sql_context(question)
    if intent in ("knowledge_query", "hybrid"):
        vec_ctx = _retrieve_vector_context(question)

    # Yield metadata first
    sources = []
    if sql_ctx and sql_ctx.get("success"):
        sources.append({"type": "SQL Database", "detail": sql_ctx.get("sql", "")})
    if vec_ctx and vec_ctx.get("sources"):
        for src in vec_ctx["sources"]:
            sources.append({"type": "Document", "detail": src})

    yield {
        "type": "meta",
        "intent": intent,
        "sources": sources,
        "sql": sql_ctx.get("sql") if sql_ctx else None,
        "dataframe": sql_ctx.get("dataframe") if sql_ctx else None,
    }

    # 3. Build context
    context_parts = []
    if sql_ctx and sql_ctx.get("context"):
        context_parts.append(f"=== DATABASE RESULTS ===\n{sql_ctx['context']}")
    if vec_ctx and vec_ctx.get("context"):
        context_parts.append(f"=== DOCUMENT KNOWLEDGE ===\n{vec_ctx['context']}")
    context_text = "\n\n".join(context_parts) if context_parts else "No context available."

    # 4. Build messages
    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    if chat_history:
        messages.extend(chat_history[-10:])
    messages.append({
        "role": "user",
        "content": (
            f"Context:\n{context_text}\n\n"
            f"Question: {question}\n\n"
            "Please answer based on the context provided above."
        ),
    })

    # 5. Stream answer
    full_answer = ""
    try:
        for chunk in llm_stream(messages, temperature=0.3, max_tokens=4096):
            delta = chunk.choices[0].delta
            if hasattr(delta, "content") and delta.content:
                full_answer += delta.content
                yield {"type": "token", "text": delta.content}
    except Exception as exc:
        error_msg = f"Error: {exc}"
        full_answer = error_msg
        yield {"type": "token", "text": error_msg}

    yield {"type": "done", "full_answer": full_answer}
