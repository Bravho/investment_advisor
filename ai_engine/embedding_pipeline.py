import time
from typing import Optional

from utils.common import configure_logging, ollama_embedding, vector_literal
from utils.db_pool import db_pool

logger = configure_logging("ai_engine.embedding")


def chunk_content(content: str, size: int = 2000, overlap: int = 100) -> list[str]:
    content = content.strip()
    if not content:
        return []
    chunks = []
    start = 0
    while start < len(content):
        end = min(len(content), start + size)
        chunks.append(content[start:end])
        if end == len(content):
            break
        start = end - overlap
    return chunks


async def run_embedding_pipeline() -> dict:
    pool = await db_pool.get_pool()
    articles = await pool.fetch(
        """
        SELECT a.id, a.title, a.content
        FROM news_articles a
        WHERE a.is_processed = TRUE
          AND NOT EXISTS (
            SELECT 1 FROM article_embeddings e WHERE e.article_id = a.id
          )
        ORDER BY a.published_at DESC NULLS LAST
        LIMIT 10
        """
    )
    embedded = 0
    chunks_created = 0
    timings: list[float] = []
    for article in articles:
        chunks = chunk_content(f"{article['title']}\n\n{article['content'] or ''}")
        if not chunks:
            continue
        try:
            vectors = []
            for chunk in chunks:
                started = time.perf_counter()
                vectors.append(await ollama_embedding(chunk))
                timings.append(time.perf_counter() - started)
            async with pool.acquire() as connection:
                async with connection.transaction():
                    await connection.execute(
                        "DELETE FROM article_embeddings WHERE article_id = $1", article["id"]
                    )
                    for index, (chunk, vector) in enumerate(zip(chunks, vectors)):
                        await connection.execute(
                            """
                            INSERT INTO article_embeddings (
                                article_id, embedding, chunk_text, chunk_index
                            ) VALUES ($1, $2::vector, $3, $4)
                            """,
                            article["id"], vector_literal(vector), chunk, index,
                        )
            embedded += 1
            chunks_created += len(chunks)
        except Exception:
            logger.exception("Embedding failed for article %s", article["id"])
    result = {
        "articles_embedded": embedded,
        "chunks_created": chunks_created,
        "avg_embedding_time": round(sum(timings) / len(timings), 4) if timings else 0,
    }
    logger.info("Embedding pipeline complete: %s", result)
    return result


async def search_similar_articles(
    query_text: str, ticker: Optional[str] = None, limit: int = 5
) -> list[dict]:
    """
    Top-k similar article chunks via pgvector.

    Fail-soft: returns [] if Ollama embeddings, pgvector, or the DB are unavailable
    so advisor context can degrade gracefully (improvement #3, 2026-10-07).
    """
    if not (query_text or "").strip():
        return []
    try:
        pool = await db_pool.get_pool()
        vector = vector_literal(await ollama_embedding(query_text.strip()))
        rows = await pool.fetch(
            """
            SELECT a.id AS article_id, a.title, a.source, a.url, a.published_at,
                   e.chunk_text, e.chunk_index,
                   e.embedding <=> $1::vector AS distance
            FROM article_embeddings e
            JOIN news_articles a ON a.id = e.article_id
            WHERE ($2::text IS NULL OR EXISTS (
              SELECT 1 FROM sentiment_scores s
              WHERE s.article_id = a.id AND s.ticker = $2
            ))
            ORDER BY distance ASC
            LIMIT $3
            """,
            vector, ticker, limit,
        )
        out = []
        for row in rows:
            item = dict(row)
            # Serialize for JSON/context consumers
            if item.get("published_at") is not None:
                item["published_at"] = item["published_at"].isoformat()
            if item.get("distance") is not None:
                item["distance"] = float(item["distance"])
            item["similarity"] = round(1.0 / (1.0 + float(item.get("distance") or 0)), 4)
            out.append(item)
        return out
    except Exception:
        logger.warning(
            "search_similar_articles unavailable (embeddings/pgvector/DB) — returning []",
            exc_info=True,
        )
        return []


def format_similar_articles_for_context(rows: list[dict], max_chars: int = 1800) -> str:
    """Compact RAG block for advisor prompts. Empty string if no rows."""
    if not rows:
        return ""
    lines = ["=== SIMILAR ARTICLES (RAG / embeddings, advisory) ==="]
    used = len(lines[0])
    for i, row in enumerate(rows, 1):
        title = (row.get("title") or "Untitled").strip()
        source = row.get("source") or "?"
        published = str(row.get("published_at") or "")[:10]
        dist = row.get("distance")
        sim = row.get("similarity")
        chunk = (row.get("chunk_text") or "").strip().replace("\n", " ")
        if len(chunk) > 280:
            chunk = chunk[:277] + "..."
        meta = f"{i}. {title} [{source} | {published}"
        if sim is not None:
            meta += f" | sim={sim}"
        elif dist is not None:
            meta += f" | dist={float(dist):.4f}"
        meta += "]"
        block = f"{meta}\n   {chunk}"
        if used + len(block) + 2 > max_chars:
            break
        lines.append(block)
        used += len(block) + 2
    return "\n".join(lines)
