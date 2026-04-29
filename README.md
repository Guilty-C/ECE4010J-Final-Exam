# VE401 Exercise Retrieval

This repo now contains the cleaned VE401 exercise bank and retrieval stack.

## Layout

- `reference/` - chapter HTML and JSONL exercise banks plus course PDFs.
- `ontology/` - course-specific formula patterns and method taxonomy.
- `retriever/` - feature extraction, indexing, and query code.
- `data/exercise_index/` - generated dense + fallback retrieval index.

## Use

Build the index:

```powershell
python -m retriever.build_exercise_index --input reference --output data/exercise_index --backend dense
```

Query similar exercises:

```powershell
python -m retriever.query_exercise_index "your question here" --index data/exercise_index --backend dense --top-k 10
```

## Notes

- Dense retrieval uses `sentence-transformers/all-MiniLM-L6-v2` with Chroma.
- The ontology reranker is tuned for VE401 chapters 15-30.
- `data/exercise_index/` is generated and can be rebuilt from `reference/`.
