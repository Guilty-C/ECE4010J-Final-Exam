from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .extract_features import (
    FORMULA_PATH,
    TAXONOMY_PATH,
    extract_features,
    feature_terms,
    iter_jsonl_records,
    load_json,
)
from .scoring import build_idf, tfidf_vector


DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION_NAME = "ve401_exercises"


def _load_dense_backend(model_name: str) -> Tuple[Dict[str, Any], Any | None, Any | None]:
    try:
        import chromadb  # type: ignore
        from sentence_transformers import SentenceTransformer  # type: ignore

        model = SentenceTransformer(model_name)
        return {"name": "chroma_sentence_transformers", "available": True, "model": model_name}, chromadb, model
    except Exception as exc:
        return {
            "name": "local_json_tfidf_fallback",
            "available": True,
            "reason": f"Chroma/SentenceTransformers unavailable: {exc.__class__.__name__}: {exc}",
        }, None, None


def _embedding_text(record: Dict[str, Any]) -> str:
    return "\n\n".join(
        str(record.get(key, ""))
        for key in ("question_text", "solution_text", "thought_text")
        if record.get(key)
    )


def _chroma_metadata(doc: Dict[str, Any]) -> Dict[str, str | int | float]:
    features = doc["features"]
    return {
        "exercise_id": str(doc["id"]),
        "chapter": str(features.get("chapter", "")),
        "method_family": str(features.get("method_family", "")),
        "procedure": str(features.get("procedure", "")),
        "task_type": str(features.get("task_type", "")),
        "parameter": str(features.get("parameter", "")),
        "formula_patterns": "|".join(features.get("formula_patterns", []) or []),
        "assumptions": "|".join(features.get("assumptions", []) or []),
        "concept_tags": "|".join(features.get("concept_tags", []) or []),
        "source_file": str(doc.get("source_file", "")),
        "source_line": int(doc.get("source_line", 0)),
    }


def build_index(input_path: Path, output_path: Path, *, model_name: str = DEFAULT_MODEL, backend: str = "auto") -> Dict[str, Any]:
    formula_ontology = load_json(FORMULA_PATH)
    method_taxonomy = load_json(TAXONOMY_PATH)
    records = list(iter_jsonl_records(input_path))
    if not records:
        raise SystemExit(
            f"No exercises_ch15.jsonl through exercises_ch30.jsonl or *_anchor_retrieval.jsonl records found under {input_path}"
        )

    docs: List[Dict[str, Any]] = []
    raw_terms = []
    for ordinal, record in enumerate(records):
        features = extract_features(record, formula_ontology=formula_ontology, method_taxonomy=method_taxonomy)
        terms = feature_terms(features)
        raw_terms.append(terms)
        docs.append(
            {
                "ordinal": ordinal,
                "id": features["id"],
                "source_file": record.get("_jsonl_path", ""),
                "source_line": record.get("_jsonl_line", 0),
                "question_text": record.get("question_text", ""),
                "solution_text": record.get("solution_text", ""),
                "thought_text": record.get("thought_text", ""),
                "text_for_embedding": _embedding_text(record),
                "features": features,
            }
        )

    idf = build_idf((terms.keys() for terms in raw_terms), len(raw_terms))
    for doc, terms in zip(docs, raw_terms):
        doc["vector"] = tfidf_vector(terms, idf)

    if output_path.exists():
        shutil.rmtree(output_path)
    output_path.mkdir(parents=True, exist_ok=True)

    with (output_path / "items.jsonl").open("w", encoding="utf-8") as fh:
        for doc in docs:
            fh.write(json.dumps(doc, ensure_ascii=False, sort_keys=True) + "\n")
    with (output_path / "idf.json").open("w", encoding="utf-8") as fh:
        json.dump(idf, fh, ensure_ascii=False, indent=2, sort_keys=True)

    if backend not in {"auto", "dense", "tfidf"}:
        raise SystemExit("--backend must be one of: auto, dense, tfidf")
    dense_backend, chromadb, model = (
        _load_dense_backend(model_name) if backend in {"auto", "dense"} else (
            {"name": "local_json_tfidf_fallback", "available": True, "reason": "Forced by --backend=tfidf"},
            None,
            None,
        )
    )
    if backend == "dense" and dense_backend["name"] != "chroma_sentence_transformers":
        raise SystemExit(str(dense_backend["reason"]))

    if chromadb is not None and model is not None:
        chroma_path = output_path / "chroma"
        client = chromadb.PersistentClient(path=str(chroma_path))
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass
        collection = client.create_collection(
            COLLECTION_NAME,
            metadata={"hnsw:space": "cosine", "schema": "ve401_formula_method_index_v1"},
        )
        embeddings = model.encode(
            [doc["text_for_embedding"] for doc in docs],
            normalize_embeddings=True,
            show_progress_bar=True,
        )
        collection.add(
            ids=[doc["id"] for doc in docs],
            documents=[doc["text_for_embedding"] for doc in docs],
            embeddings=[emb.tolist() for emb in embeddings],
            metadatas=[_chroma_metadata(doc) for doc in docs],
        )
    else:
        dense_backend = dense_backend

    config = {
        "item_count": len(docs),
        "backend": dense_backend,
        "input": str(input_path),
        "collection": COLLECTION_NAME,
        "formula_ontology": str(FORMULA_PATH.relative_to(Path.cwd()) if FORMULA_PATH.is_relative_to(Path.cwd()) else FORMULA_PATH),
        "method_taxonomy": str(TAXONOMY_PATH.relative_to(Path.cwd()) if TAXONOMY_PATH.is_relative_to(Path.cwd()) else TAXONOMY_PATH),
        "schema": "ve401_formula_method_index_v1",
    }
    with (output_path / "config.json").open("w", encoding="utf-8") as fh:
        json.dump(config, fh, ensure_ascii=False, indent=2, sort_keys=True)
    return config


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a VE401 formula/method exercise index.")
    parser.add_argument(
        "--input",
        default="reference",
        help="Directory containing exercises_ch15.jsonl ... exercises_ch30.jsonl and optional *_anchor_retrieval.jsonl files",
    )
    parser.add_argument("--output", default="data/exercise_index", help="Output index directory")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="SentenceTransformers model name for dense Chroma indexing")
    parser.add_argument("--backend", default="auto", choices=["auto", "dense", "tfidf"], help="Index backend")
    args = parser.parse_args()
    config = build_index(Path(args.input), Path(args.output), model_name=args.model, backend=args.backend)
    print(json.dumps(config, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
