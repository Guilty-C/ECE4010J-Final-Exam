"""Phase D — template retrieval over data/corpus.jsonl."""
from retriever.retrieve import (
    Retriever,
    RetrievalHit,
    get_retriever,
    retrieve,
    retrieve_for_card,
)

__all__ = [
    "Retriever",
    "RetrievalHit",
    "get_retriever",
    "retrieve",
    "retrieve_for_card",
]
