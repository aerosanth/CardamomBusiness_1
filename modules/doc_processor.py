"""
Document Processor — Parse, Chunk & Embed documents into ChromaDB.
==================================================================

Pipeline:
  File / URL  →  Docling (parse)  →  chunks  →  embed  →  ChromaDB

Supported input formats (via Docling):
  PDF, DOCX, XLSX, PPTX, HTML, PNG, JPG, and more.

For each document the processor:
  1. Converts to a structured DoclingDocument (text, tables, images).
  2. Chunks into semantically meaningful segments.
  3. Generates embeddings (text via Gemini, images via vision-describe-then-embed).
  4. Stores vectors + metadata in a persistent ChromaDB collection.
"""

from __future__ import annotations

import os
import hashlib
import tempfile
from datetime import datetime
from typing import Any, Optional, List, Dict

import chromadb

# ── Paths ──
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHROMA_DIR = os.path.join(_PROJECT_ROOT, "data", "chroma_db")
UPLOAD_DIR = os.path.join(_PROJECT_ROOT, "uploaded_docs")
COLLECTION_NAME = "cardamom_knowledge"


# ═══════════════════════════════════════════════════════════════════════
#  ChromaDB helpers
# ═══════════════════════════════════════════════════════════════════════

def _get_chroma_client() -> chromadb.ClientAPI:
    os.makedirs(CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(path=CHROMA_DIR)


def get_collection() -> chromadb.Collection:
    """Get or create the main knowledge-base collection.

    We manage embeddings ourselves (pass raw vectors),
    so we use a dummy embedding function.
    """
    client = _get_chroma_client()

    class _NoopEmbedding(chromadb.EmbeddingFunction):
        def __call__(self, input):
            raise RuntimeError("External embeddings required")

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def get_indexed_documents() -> List[Dict[str, Any]]:
    """Return a summary of all indexed documents (unique source files)."""
    try:
        coll = get_collection()
        all_meta = coll.get(include=["metadatas"])
        if not all_meta or not all_meta["metadatas"]:
            return []

        docs: dict[str, dict] = {}
        for meta in all_meta["metadatas"]:
            src = meta.get("source", "unknown")
            if src not in docs:
                docs[src] = {
                    "source": src,
                    "chunk_count": 0,
                    "indexed_at": meta.get("indexed_at", ""),
                    "doc_type": meta.get("doc_type", "unknown"),
                }
            docs[src]["chunk_count"] += 1

        return list(docs.values())
    except Exception:
        return []


def get_total_chunks() -> int:
    try:
        return get_collection().count()
    except Exception:
        return 0


def delete_document(source_name: str) -> int:
    """Remove all chunks belonging to a specific source document."""
    coll = get_collection()
    # ChromaDB where filter
    results = coll.get(where={"source": source_name}, include=[])
    if results and results["ids"]:
        coll.delete(ids=results["ids"])
        return len(results["ids"])
    return 0


# ═══════════════════════════════════════════════════════════════════════
#  Document parsing via Docling
# ═══════════════════════════════════════════════════════════════════════

def _parse_with_docling(file_path: str) -> List[Dict]:
    """Use Docling to parse a document into structured chunks.

    Returns a list of dicts, each with:
      - text: str
      - chunk_type: 'text' | 'table' | 'image_description'
      - page: int | None
      - metadata: dict
    """
    try:
        from docling.document_converter import DocumentConverter

        converter = DocumentConverter()
        result = converter.convert(file_path)
        doc = result.document

        chunks = []

        # Export as markdown and split into sections
        md_content = doc.export_to_markdown()
        if md_content and md_content.strip():
            # Split markdown into reasonably sized chunks
            sections = _split_markdown(md_content)
            for i, section in enumerate(sections):
                if section.strip():
                    chunks.append({
                        "text": section.strip(),
                        "chunk_type": "text",
                        "page": None,
                        "metadata": {"section_index": i},
                    })

        # If Docling produced no output, try simple text extraction
        if not chunks:
            chunks = _fallback_parse(file_path)

        return chunks

    except ImportError:
        # Docling not installed — use fallback
        return _fallback_parse(file_path)
    except Exception as exc:
        print(f"[doc_processor] Docling error: {exc}", flush=True)
        return _fallback_parse(file_path)


def _split_markdown(text: str, max_chunk_size: int = 1500) -> List[str]:
    """Split markdown text into chunks, preferring heading boundaries."""
    import re

    # Split on markdown headings (## or ###)
    sections = re.split(r"\n(?=#{1,3}\s)", text)

    chunks = []
    for section in sections:
        if len(section) <= max_chunk_size:
            chunks.append(section)
        else:
            # Further split large sections by paragraphs
            paragraphs = section.split("\n\n")
            current = ""
            for para in paragraphs:
                if len(current) + len(para) + 2 > max_chunk_size and current:
                    chunks.append(current)
                    current = para
                else:
                    current = current + "\n\n" + para if current else para
            if current:
                chunks.append(current)

    return [c for c in chunks if c.strip()]


def _fallback_parse(file_path: str) -> List[Dict]:
    """Minimal fallback when Docling is unavailable.

    Handles plain text and basic file reading.
    """
    chunks = []
    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext in (".txt", ".md", ".csv"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            for i, section in enumerate(_split_markdown(text)):
                chunks.append({
                    "text": section,
                    "chunk_type": "text",
                    "page": None,
                    "metadata": {"section_index": i},
                })
        elif ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
            # Describe the image via LLM
            with open(file_path, "rb") as f:
                image_bytes = f.read()
            from modules.llm_provider import describe_image
            desc = describe_image(image_bytes)
            chunks.append({
                "text": desc,
                "chunk_type": "image_description",
                "page": None,
                "metadata": {"original_file": os.path.basename(file_path)},
            })
        else:
            # Try reading as plain text
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
            if text.strip():
                for i, section in enumerate(_split_markdown(text)):
                    chunks.append({
                        "text": section,
                        "chunk_type": "text",
                        "page": None,
                        "metadata": {"section_index": i},
                    })
    except Exception as exc:
        print(f"[doc_processor] Fallback parse error: {exc}", flush=True)

    return chunks


# ═══════════════════════════════════════════════════════════════════════
#  URL scraping
# ═══════════════════════════════════════════════════════════════════════

def download_from_url(url: str) -> Optional[str]:
    """Download a file from a URL into uploaded_docs/.

    For web pages, saves the HTML. For direct file links (PDF, etc.),
    saves the binary file.

    Returns the local file path or None on failure.
    """
    import requests
    from urllib.parse import urlparse

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    try:
        resp = requests.get(url, timeout=30, verify=False, stream=True)
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path) or "downloaded_page"

        # Determine extension from content type if filename lacks one
        ext = os.path.splitext(filename)[1].lower()
        if not ext:
            if "pdf" in content_type:
                filename += ".pdf"
            elif "html" in content_type:
                filename += ".html"
            elif "image" in content_type:
                filename += ".png"
            else:
                filename += ".html"

        # Add hash to avoid collisions
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        safe_name = f"{url_hash}_{filename}"
        local_path = os.path.join(UPLOAD_DIR, safe_name)

        with open(local_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        print("[doc_processor] Downloaded %s -> %s" % (url, local_path), flush=True)
        return local_path

    except Exception as exc:
        print(f"[doc_processor] Download error for {url}: {exc}", flush=True)
        return None


def scrape_webpage_text(url: str) -> Optional[str]:
    """Scrape visible text from a web page (for non-downloadable URLs)."""
    import requests
    from bs4 import BeautifulSoup

    try:
        resp = requests.get(url, timeout=30, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove script/style elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        text = soup.get_text(separator="\n", strip=True)
        return text if text.strip() else None

    except Exception as exc:
        print(f"[doc_processor] Scrape error for {url}: {exc}", flush=True)
        return None


# ═══════════════════════════════════════════════════════════════════════
#  Main ingestion pipeline
# ═══════════════════════════════════════════════════════════════════════

def process_file(
    file_path: str,
    source_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Full pipeline: parse → chunk → embed → store in ChromaDB.

    Args:
        file_path: Path to the local file.
        source_name: Human-readable name (defaults to filename).

    Returns:
        Summary dict with keys: source, chunks_created, status.
    """
    from modules.llm_provider import embed_texts

    source = source_name or os.path.basename(file_path)
    timestamp = datetime.now().isoformat()

    # 1. Parse
    chunks = _parse_with_docling(file_path)
    if not chunks:
        return {"source": source, "chunks_created": 0, "status": "no_content"}

    # 2. Prepare texts & metadata for embedding
    texts = [c["text"] for c in chunks if c["text"].strip()]
    if not texts:
        return {"source": source, "chunks_created": 0, "status": "no_text"}

    metadatas = []
    ids = []
    for i, chunk in enumerate(chunks):
        if not chunk["text"].strip():
            continue
        chunk_id = f"{hashlib.md5(source.encode()).hexdigest()[:10]}_{i}"
        ids.append(chunk_id)
        metadatas.append({
            "source": source,
            "chunk_type": chunk["chunk_type"],
            "chunk_index": i,
            "indexed_at": timestamp,
            "doc_type": os.path.splitext(file_path)[1].lower(),
        })

    # 3. Generate embeddings
    try:
        embeddings = embed_texts(texts)
    except Exception as exc:
        return {"source": source, "chunks_created": 0, "status": f"embedding_error: {exc}"}

    # 4. Store in ChromaDB
    try:
        coll = get_collection()

        # Remove old chunks for the same source (re-index)
        delete_document(source)

        coll.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        return {
            "source": source,
            "chunks_created": len(ids),
            "status": "success",
        }

    except Exception as exc:
        return {"source": source, "chunks_created": 0, "status": f"chroma_error: {exc}"}


def process_uploaded_bytes(
    file_bytes: bytes,
    filename: str,
) -> Dict[str, Any]:
    """Process an in-memory file (e.g. from Streamlit file uploader).

    Saves to uploaded_docs/ then runs the full pipeline.
    """
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    local_path = os.path.join(UPLOAD_DIR, filename)
    with open(local_path, "wb") as f:
        f.write(file_bytes)

    return process_file(local_path, source_name=filename)


def process_url(url: str) -> Dict[str, Any]:
    """Download content from a URL and run the full pipeline."""
    # First try to download as a file (PDF, images, etc.)
    local_path = download_from_url(url)
    if local_path:
        return process_file(local_path, source_name=url)

    # Fallback: scrape web page text
    text = scrape_webpage_text(url)
    if not text:
        return {"source": url, "chunks_created": 0, "status": "download_failed"}

    # Save scraped text and process
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    local_path = os.path.join(UPLOAD_DIR, f"{url_hash}_webpage.txt")
    with open(local_path, "w", encoding="utf-8") as f:
        f.write(text)

    return process_file(local_path, source_name=url)


# ═══════════════════════════════════════════════════════════════════════
#  Vector search
# ═══════════════════════════════════════════════════════════════════════

def search_similar(query: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """Search the vector DB for chunks similar to the query.

    Returns list of dicts with: text, source, score, chunk_type.
    """
    from modules.llm_provider import embed_query

    try:
        coll = get_collection()
        if coll.count() == 0:
            return []

        query_embedding = embed_query(query)
        results = coll.query(
            query_embeddings=[query_embedding],
            n_results=min(n_results, coll.count()),
            include=["documents", "metadatas", "distances"],
        )

        hits = []
        if results and results["documents"]:
            for doc, meta, dist in zip(
                results["documents"][0],
                results["metadatas"][0],
                results["distances"][0],
            ):
                hits.append({
                    "text": doc,
                    "source": meta.get("source", "unknown"),
                    "chunk_type": meta.get("chunk_type", "text"),
                    "score": 1 - dist,  # cosine distance → similarity
                })

        return hits

    except Exception as exc:
        print(f"[doc_processor] Search error: {exc}", flush=True)
        return []
