"""Collects Discord messages into the Chroma vector store for semantic recall.

Uses the vector store's async methods so embedding + persistence never block the
Discord event loop, and keys documents by message id so re-collecting the same
message updates in place instead of creating duplicates.
"""
from __future__ import annotations

from typing import List

from langchain_core.documents import Document

from scrumbot.data.chroma import ChromaManager


class DiscordChatCollector:
    """Persist and semantically search Discord chat history."""

    def __init__(self, chroma_manager: ChromaManager) -> None:
        self._vectorstore = chroma_manager.get_vectorstore()

    async def save_message(
        self,
        message_id: str,
        author: str,
        content: str,
        timestamp: str,
        channel: str,
    ) -> None:
        """Store a single Discord message (no-op for empty content)."""
        if not content or not content.strip():
            return
        doc = Document(
            page_content=content,
            metadata={
                "message_id": message_id,
                "author": author,
                "timestamp": timestamp,
                "channel": channel,
            },
        )
        # Async wrapper runs the embed + write off the event loop; the id makes
        # the operation idempotent.
        await self._vectorstore.aadd_documents([doc], ids=[message_id])

    async def search_messages(self, query: str, k: int = 5) -> List[Document]:
        """Return the ``k`` most semantically similar stored messages."""
        return await self._vectorstore.asimilarity_search(query, k=k)
