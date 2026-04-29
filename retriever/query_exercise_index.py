from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from .extract_features import extract_features, feature_terms, load_json
from .scoring import cosine_similarity, rerank, tfidf_vector
from .build_exercise_index import COLLECTION_NAME, DEFAULT_MODEL


def _load_items(index_path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    with (index_path / "items.jsonl").open("r", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                items.append(json.loads(line))
    return items


def _dense_candidates(
    query: str,
    index_path: Path,
    item_by_id: Dict[str, Dict[str, Any]],
    *,
    pool_size: int,
) -> List[Dict[str, Any]] | None:
    config_path = index_path / "config.json"
    if not config_path.exists():
        return None
    config = load_json(config_path)
    backend = config.get("backend", {})
    if backend.get("name") != "chroma_sentence_transformers":
        return None
    try:
        import chromadb  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore

        model = SentenceTransformer(str(backend.get("model") or DEFAULT_MODEL))
        client = chromadb.PersistentClient(path=str(index_path / "chroma"))
        collection = client.get_collection(str(config.get("collection") or COLLECTION_NAME))
        query_embedding = model.encode([query], normalize_embeddings=True)[0].tolist()
        raw = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(pool_size, len(item_by_id)),
            include=["distances"],
        )
    except Exception:
        return None

    ids = raw.get("ids", [[]])[0]
    distances = raw.get("distances", [[]])[0]
    candidates: List[Dict[str, Any]] = []
    for item_id, distance in zip(ids, distances):
        item = item_by_id.get(str(item_id))
        if not item:
            continue
        vector_score = max(0.0, 1.0 - float(distance))
        candidates.append(
            {
                "id": item["id"],
                "source_file": item.get("source_file", ""),
                "source_line": item.get("source_line", 0),
                "question_text": item.get("question_text", ""),
                "features": item["features"],
                "vector_score": round(vector_score, 6),
            }
        )
    return candidates


class ExerciseIndex:
    def __init__(self, index_path: Path, *, backend: str = "auto") -> None:
        if backend not in {"auto", "dense", "tfidf"}:
            raise ValueError("backend must be one of: auto, dense, tfidf")
        self.index_path = index_path
        self.backend = backend
        self.items = _load_items(index_path)
        self.item_by_id = {item["id"]: item for item in self.items}
        self.idf: Dict[str, float] | None = None
        self.config = load_json(index_path / "config.json") if (index_path / "config.json").exists() else {}
        self._dense_model = None
        self._dense_collection = None
        self._dense_available = False
        self._initialise_dense()

    def _initialise_dense(self) -> None:
        if self.backend == "tfidf":
            return
        backend = self.config.get("backend", {})
        if backend.get("name") != "chroma_sentence_transformers":
            return
        try:
            import chromadb  # type: ignore
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._dense_model = SentenceTransformer(str(backend.get("model") or DEFAULT_MODEL))
            client = chromadb.PersistentClient(path=str(self.index_path / "chroma"))
            self._dense_collection = client.get_collection(str(self.config.get("collection") or COLLECTION_NAME))
            self._dense_available = True
        except Exception:
            self._dense_model = None
            self._dense_collection = None
            self._dense_available = False

    def _dense_candidates(self, query: str, *, pool_size: int) -> List[Dict[str, Any]] | None:
        if not self._dense_available or self._dense_model is None or self._dense_collection is None:
            return None
        try:
            query_embedding = self._dense_model.encode([query], normalize_embeddings=True)[0].tolist()
            raw = self._dense_collection.query(
                query_embeddings=[query_embedding],
                n_results=min(pool_size, len(self.item_by_id)),
                include=["distances"],
            )
        except Exception:
            return None

        ids = raw.get("ids", [[]])[0]
        distances = raw.get("distances", [[]])[0]
        candidates: List[Dict[str, Any]] = []
        for item_id, distance in zip(ids, distances):
            item = self.item_by_id.get(str(item_id))
            if not item:
                continue
            vector_score = max(0.0, 1.0 - float(distance))
            candidates.append(
                {
                    "id": item["id"],
                    "source_file": item.get("source_file", ""),
                    "source_line": item.get("source_line", 0),
                    "question_text": item.get("question_text", ""),
                    "features": item["features"],
                    "vector_score": round(vector_score, 6),
                }
            )
        return candidates

    def _tfidf_candidates(self, query_features: Dict[str, Any], *, pool_size: int) -> List[Dict[str, Any]]:
        if self.idf is None:
            self.idf = load_json(self.index_path / "idf.json")
        query_vector = tfidf_vector(feature_terms(query_features), self.idf)

        candidates: List[Dict[str, Any]] = []
        for item in self.items:
            vector_score = cosine_similarity(query_vector, item.get("vector", {}))
            if vector_score <= 0 and not (set(query_features.get("formula_patterns", [])) & set(item["features"].get("formula_patterns", []))):
                continue
            candidates.append(
                {
                    "id": item["id"],
                    "source_file": item.get("source_file", ""),
                    "source_line": item.get("source_line", 0),
                    "question_text": item.get("question_text", ""),
                    "features": item["features"],
                    "vector_score": round(vector_score, 6),
                }
            )
        candidates.sort(key=lambda item: (-float(item["vector_score"]), str(item["id"])))
        return candidates[:pool_size]

    def query(self, query: str, *, top_k: int = 10, pool_size: int = 50) -> List[Dict[str, Any]]:
        query_record = {"id": "query", "question_text": query, "solution_text": "", "thought_text": ""}
        query_features = extract_features(query_record)
        dense_candidates = None if self.backend == "tfidf" else self._dense_candidates(query, pool_size=pool_size)
        if self.backend == "dense" and dense_candidates is None:
            raise RuntimeError("Dense Chroma index is unavailable. Rebuild with --backend dense or use --backend tfidf.")
        tfidf_candidates = self._tfidf_candidates(query_features, pool_size=pool_size)
        candidates_by_id: Dict[str, Dict[str, Any]] = {}
        for source, source_candidates in (("dense", dense_candidates or []), ("tfidf", tfidf_candidates)):
            for candidate in source_candidates:
                candidate_id = str(candidate["id"])
                existing = candidates_by_id.get(candidate_id)
                if existing is None or float(candidate["vector_score"]) > float(existing.get("vector_score", 0.0)):
                    merged = dict(candidate)
                    merged["retrieval_source"] = source
                    candidates_by_id[candidate_id] = merged
                elif existing:
                    existing["retrieval_source"] = f"{existing.get('retrieval_source', '')}+{source}"
        candidates = list(candidates_by_id.values())
        return rerank(query_features, candidates, top_k=top_k)


def _tfidf_candidates(
    query_features: Dict[str, Any],
    index_path: Path,
    items: List[Dict[str, Any]],
    *,
    pool_size: int,
) -> List[Dict[str, Any]]:
    idf = load_json(index_path / "idf.json")
    query_vector = tfidf_vector(feature_terms(query_features), idf)

    candidates: List[Dict[str, Any]] = []
    for item in items:
        vector_score = cosine_similarity(query_vector, item.get("vector", {}))
        if vector_score <= 0 and not (set(query_features.get("formula_patterns", [])) & set(item["features"].get("formula_patterns", []))):
            continue
        candidates.append(
            {
                "id": item["id"],
                "source_file": item.get("source_file", ""),
                "source_line": item.get("source_line", 0),
                "question_text": item.get("question_text", ""),
                "features": item["features"],
                "vector_score": round(vector_score, 6),
            }
        )
    candidates.sort(key=lambda item: (-float(item["vector_score"]), str(item["id"])))
    return candidates[:pool_size]


def query_index(query: str, index_path: Path, *, top_k: int = 10, pool_size: int = 50, backend: str = "auto") -> List[Dict[str, Any]]:
    return ExerciseIndex(index_path, backend=backend).query(query, top_k=top_k, pool_size=pool_size)


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the VE401 formula/method exercise index.")
    parser.add_argument("query", help="Question text to retrieve similar exercises for")
    parser.add_argument("--index", default="data/exercise_index", help="Index directory")
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--pool-size", type=int, default=50)
    parser.add_argument("--backend", default="auto", choices=["auto", "dense", "tfidf"])
    parser.add_argument("--json", action="store_true", help="Emit full JSON results")
    args = parser.parse_args()

    results = query_index(args.query, Path(args.index), top_k=args.top_k, pool_size=args.pool_size, backend=args.backend)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    for rank, hit in enumerate(results, start=1):
        features = hit["features"]
        print(
            f"{rank}. {hit['id']} score={hit['score']:.4f} vector={hit['vector_score']:.4f} "
            f"overlap={hit['overlap_score']:.2f} chapter={features.get('chapter')} "
            f"procedure={features.get('procedure')} task={features.get('task_type')} parameter={features.get('parameter')}"
        )
        print(f"   {hit['question_text'][:220].replace(chr(10), ' ')}")
        if hit.get("overlap_reasons"):
            print(f"   overlap: {json.dumps(hit['overlap_reasons'], ensure_ascii=False, sort_keys=True)}")


if __name__ == "__main__":
    main()
