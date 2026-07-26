"""
Knowledge Base Tab — Upload / URL + RAG Chatbot.
=================================================

Layout:
  ┌─────────────────────────────────────────────┐
  │  Add Knowledge Source (Upload file / URL)    │
  │  Indexed Documents list                      │
  ├─────────────────────────────────────────────┤
  │  💬 AI Chat — answers from SQL + Vector DB   │
  └─────────────────────────────────────────────┘
"""

from __future__ import annotations

import streamlit as st


# ═══════════════════════════════════════════════════════════════════════
#  Source management UI
# ═══════════════════════════════════════════════════════════════════════

def _render_add_source() -> None:
    """Render the file-upload / URL input panel."""

    st.markdown("### 📥 Add Knowledge Source")

    source_type = st.radio(
        "Choose source type:",
        ["📄 Upload File", "🌐 Provide Web URL"],
        horizontal=True,
        label_visibility="collapsed",
    )

    if source_type == "📄 Upload File":
        uploaded = st.file_uploader(
            "Upload a document (PDF, DOCX, XLSX, TXT, Image)",
            type=["pdf", "docx", "xlsx", "xls", "txt", "csv", "md",
                  "png", "jpg", "jpeg", "gif", "webp", "pptx", "html"],
            accept_multiple_files=False,
        )

        if uploaded is not None:
            st.info(f"📎 **{uploaded.name}** ({uploaded.size / 1024:.1f} KB)")

            if st.button("🚀 Process & Index", key="btn_upload"):
                with st.spinner(f"Processing {uploaded.name} …"):
                    from modules.doc_processor import process_uploaded_bytes

                    result = process_uploaded_bytes(
                        file_bytes=uploaded.getvalue(),
                        filename=uploaded.name,
                    )

                if result["status"] == "success":
                    st.success(
                        f"✅ Indexed **{result['source']}** — "
                        f"{result['chunks_created']} chunks created."
                    )
                else:
                    st.error(f"❌ Processing failed: {result['status']}")

    else:  # Web URL
        url = st.text_input(
            "Enter URL to scrape:",
            placeholder="https://example.com/report.pdf",
        )

        if url and st.button("🌐 Scrape & Index", key="btn_url"):
            with st.spinner(f"Downloading and processing {url} …"):
                from modules.doc_processor import process_url

                result = process_url(url)

            if result["status"] == "success":
                st.success(
                    f"✅ Indexed **{result['source']}** — "
                    f"{result['chunks_created']} chunks created."
                )
            else:
                st.error(f"❌ Processing failed: {result['status']}")


def _render_indexed_docs() -> None:
    """Show a list of all indexed documents."""
    from modules.doc_processor import get_indexed_documents, get_total_chunks

    docs = get_indexed_documents()
    total = get_total_chunks()

    if not docs:
        st.caption("No documents indexed yet. Upload a file or provide a URL above.")
        return

    st.markdown(f"### 📋 Indexed Documents  ({total} total chunks)")
    for doc in docs:
        col1, col2, col3 = st.columns([4, 1, 1])
        with col1:
            icon = "📄" if doc["doc_type"] in (".pdf", ".docx", ".txt") else "🌐"
            st.markdown(f"{icon} **{doc['source']}**")
        with col2:
            st.caption(f"{doc['chunk_count']} chunks")
        with col3:
            if st.button("🗑️", key=f"del_{doc['source']}", help="Remove"):
                from modules.doc_processor import delete_document
                deleted = delete_document(doc["source"])
                st.toast(f"Removed {deleted} chunks from {doc['source']}")
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════
#  Chat UI
# ═══════════════════════════════════════════════════════════════════════

def _render_chat() -> None:
    """Render the RAG chatbot interface."""

    st.markdown("### 💬 Chat with Your Data")
    st.caption(
        "Ask questions about cardamom prices, production, or uploaded documents. "
        "The AI searches both the SQL database and the knowledge base."
    )

    # ── Session state for chat history ──
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = [
            {
                "role": "assistant",
                "content": (
                    "Hello! 🌿 I'm your Cardamom Business AI assistant.\n\n"
                    "I can answer questions using:\n"
                    "- 📊 **Price data** from the auction database\n"
                    "- 📄 **Documents** you've uploaded\n\n"
                    "Try asking: *\"What was the highest cardamom price this year?\"*"
                ),
            }
        ]

    # ── Display chat history ──
    for msg in st.session_state.chat_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

            # Show SQL query if available
            if msg.get("sql"):
                with st.expander("🔍 SQL Query"):
                    st.code(msg["sql"], language="sql")

            # Show data table if available
            if msg.get("dataframe") is not None:
                with st.expander("📊 Query Results"):
                    st.dataframe(msg["dataframe"], use_container_width=True)

            # Show sources if available
            if msg.get("sources"):
                with st.expander("📚 Sources"):
                    for src in msg["sources"]:
                        st.caption(f"• {src['type']}: {src['detail']}")

    # ── Chat input ──
    user_input = st.chat_input("Ask a question about cardamom …")

    if user_input:
        # Add user message
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        # Generate response
        with st.chat_message("assistant"):
            with st.spinner("Thinking …"):
                try:
                    from modules.rag_engine import ask

                    # Build history for context (only role + content)
                    history = [
                        {"role": m["role"], "content": m["content"]}
                        for m in st.session_state.chat_messages[-10:]
                    ]

                    result = ask(user_input, chat_history=history)

                    st.markdown(result["answer"])

                    # Show SQL if used
                    if result.get("sql"):
                        with st.expander("🔍 SQL Query"):
                            st.code(result["sql"], language="sql")

                    # Show result table if available
                    if result.get("dataframe") is not None and not result["dataframe"].empty:
                        with st.expander("📊 Query Results"):
                            st.dataframe(result["dataframe"], use_container_width=True)

                    # Show sources
                    if result.get("sources"):
                        with st.expander("📚 Sources"):
                            for src in result["sources"]:
                                st.caption(f"• {src['type']}: {src['detail']}")

                    # Save to history
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": result["answer"],
                        "sql": result.get("sql"),
                        "dataframe": result.get("dataframe"),
                        "sources": result.get("sources"),
                    })

                except Exception as exc:
                    error_msg = f"Sorry, I encountered an error: {exc}"
                    st.error(error_msg)
                    st.session_state.chat_messages.append({
                        "role": "assistant",
                        "content": error_msg,
                    })

    # ── Clear chat button ──
    if len(st.session_state.chat_messages) > 1:
        if st.button("🗑️ Clear Chat", key="clear_chat"):
            st.session_state.chat_messages = [st.session_state.chat_messages[0]]
            st.rerun()


# ═══════════════════════════════════════════════════════════════════════
#  Main render
# ═══════════════════════════════════════════════════════════════════════

def render_knowledge_base() -> None:
    """Entry point — called from the main app."""

    # Two-column layout: source mgmt (left) + chat (right)
    col_left, col_right = st.columns([1, 2], gap="large")

    with col_left:
        _render_add_source()
        st.markdown("---")
        _render_indexed_docs()

    with col_right:
        _render_chat()
