"""Retrieval helpers for VE401 exercises."""

try:
    from retriever.retrieve import (
        Retriever,
        RetrievalHit,
        get_retriever,
        retrieve,
        retrieve_for_card,
    )
except ModuleNotFoundError:
    __all__ = []
else:
    __all__ = [
        "Retriever",
        "RetrievalHit",
        "get_retriever",
        "retrieve",
        "retrieve_for_card",
    ]
