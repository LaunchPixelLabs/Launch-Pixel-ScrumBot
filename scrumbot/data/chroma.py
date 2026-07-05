"""In-process ChromaDB vector store.

Defaults to a local ONNX embedding model via ``fastembed`` so semantic search
needs no API key and no network round-trip -- this is what makes the sub-second,
"in-process" search in the benchmarks real. Set ``EMBEDDING_PROVIDER=openai`` to
use hosted embeddings instead.

A single manager is constructed and owned by the application container; the old
``__new__`` singleton hack (which silently ignored constructor arguments) is
gone in favour of explicit dependency injection.
"""
from __future__ import annotations

import logging
from typing import Optional

from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings

from scrumbot.config import Settings, get_settings

logger = logging.getLogger(__name__)

_DEFAULT_OPENAI_EMBED_MODEL = "text-embedding-3-small"


def _build_embeddings(settings: Settings) -> Embeddings:
    if settings.embedding_provider == "openai":
        from langchain_openai import OpenAIEmbeddings

        # ``embedding_model`` defaults to a fastembed (namespaced) model; if the
        # operator kept that default while selecting OpenAI, fall back sensibly.
        model = (
            settings.embedding_model
            if "/" not in settings.embedding_model
            else _DEFAULT_OPENAI_EMBED_MODEL
        )
        kwargs = {"api_key": settings.openai_api_key} if settings.openai_api_key else {}
        logger.info("Using OpenAI embeddings (%s)", model)
        return OpenAIEmbeddings(model=model, **kwargs)

    from langchain_community.embeddings import FastEmbedEmbeddings

    logger.info("Using local fastembed embeddings (%s)", settings.embedding_model)
    return FastEmbedEmbeddings(model_name=settings.embedding_model)


class ChromaManager:
    """Owns the persistent Chroma vector store and its embedding function."""

    def __init__(self, settings: Optional[Settings] = None) -> None:
        self._settings = settings or get_settings()
        self._embeddings = _build_embeddings(self._settings)
        self.vectorstore = Chroma(
            collection_name=self._settings.chroma_collection,
            persist_directory=self._settings.chroma_db_path,
            embedding_function=self._embeddings,
        )

    def get_vectorstore(self) -> Chroma:
        """Return the underlying Chroma vector store."""
        return self.vectorstore
