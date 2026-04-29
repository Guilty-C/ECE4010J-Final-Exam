from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List

ROOT = Path(__file__).resolve().parents[1]
FORMULA_PATH = ROOT / "ontology" / "ve401_formula_patterns.json"
TAXONOMY_PATH = ROOT / "ontology" / "ve401_method_taxonomy.json"

TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\\-]*|\\[A-Za-z]+|\d+(?:\.\d+)?")
SYMBOL_RE = re.compile(
    r"\\(?:bar|hat)?\s*[A-Za-z]+|\\(?:mu|sigma|alpha|beta|chi|lambda)|"
    r"\b(?:xbar|mu|sigma|alpha|beta|df|p-value|pvalue|n|s\^2|s|z|t|F|r\^2|R\^2)\b"
)

STOPWORDS = {
    "the", "and", "for", "with", "from", "that", "this", "there", "where", "when",
    "what", "which", "into", "over", "under", "then", "than", "use", "using", "has",
    "have", "had", "are", "was", "were", "been", "being", "sample", "random",
}


def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _normalise_text(record: Dict[str, Any]) -> str:
    return "\n".join(
        str(record.get(k, ""))
        for k in ("question_text", "solution_text", "thought_text", "source")
        if record.get(k)
    )


def _tokens(text: str) -> List[str]:
    out: List[str] = []
    for match in TOKEN_RE.finditer(text.lower()):
        token = match.group(0).strip("\\")
        if len(token) < 2 or token in STOPWORDS:
            continue
        out.append(token)
    return out


def _contains_keyword(text_lower: str, keyword: str) -> bool:
    return keyword.lower().replace("\\\\", "\\") in text_lower


def _match_formula_patterns(text: str, patterns: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    text_lower = text.lower()
    hits: List[Dict[str, Any]] = []
    for pattern in patterns:
        pattern_id = str(pattern.get("id", ""))
        if (
            pattern_id.startswith("chi_square_variance")
            and "chi" not in text_lower
            and not _contains_keyword(text_lower, "test sigma")
            and not _contains_keyword(text_lower, "test whether sigma")
            and not _contains_keyword(text_lower, "test variance")
            and not ("s^2" in text_lower and "sigma" in text_lower)
            and not ("s squared" in text_lower and "sigma" in text_lower)
        ):
            continue
        keyword_score = 0
        regex_score = 0
        for keyword in pattern.get("keywords", []):
            if _contains_keyword(text_lower, keyword):
                keyword_score += 2
        for regex in pattern.get("regex", []):
            try:
                if re.search(regex, text, flags=re.IGNORECASE):
                    regex_score += 3
            except re.error:
                continue
        score = keyword_score + regex_score
        # Avoid broad false positives such as generic "test" or regression
        # residual variance s^2. A formula hit needs either strong keyword
        # evidence or a formula cue plus a method-specific keyword cue.
        if not (keyword_score >= 4 or (keyword_score >= 2 and regex_score >= 3) or regex_score >= 6):
            score = 0
        if score:
            hit = dict(pattern)
            hit["match_score"] = score
            hits.append(hit)
    hits.sort(key=lambda x: (-int(x["match_score"]), str(x["id"])))
    return hits


def _chapter_from_record(record: Dict[str, Any]) -> str:
    source = str(record.get("source", ""))
    rec_id = str(record.get("id", ""))
    match = re.search(r"ch(?:apter)?[_\s-]*(\d{1,2})", source + " " + rec_id, flags=re.IGNORECASE)
    return match.group(1) if match else ""


def _taxonomy_matches(text: str, taxonomy: Dict[str, Any], key: str) -> List[str]:
    text_lower = text.lower()
    matched: List[str] = []
    for name, keywords in taxonomy.get(key, {}).items():
        if any(_contains_keyword(text_lower, str(keyword)) for keyword in keywords):
            matched.append(name)
    return sorted(matched)


def _symbols(text: str) -> List[str]:
    found = {m.group(0).replace(" ", "") for m in SYMBOL_RE.finditer(text)}
    return sorted(found)


def extract_features(
    record: Dict[str, Any],
    *,
    formula_ontology: Dict[str, Any] | None = None,
    method_taxonomy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    formula_ontology = formula_ontology or load_json(FORMULA_PATH)
    method_taxonomy = method_taxonomy or load_json(TAXONOMY_PATH)
    text = _normalise_text(record)
    chapter = _chapter_from_record(record)
    chapter_hints = method_taxonomy.get("chapter_hints", {}).get(chapter, [])
    task_matches = _taxonomy_matches(text, method_taxonomy, "task_type_keywords")
    parameter_matches = _taxonomy_matches(text, method_taxonomy, "parameter_keywords")
    pattern_hits = _match_formula_patterns(text, formula_ontology.get("patterns", []))
    best = pattern_hits[0] if pattern_hits else {}
    if pattern_hits and task_matches:
        preferred_tasks = ["hypothesis_test", "confidence_interval", "regression_inference", "regression_modeling"]
        preferred_task = next((task for task in preferred_tasks if task in task_matches), task_matches[0])
        task_best = next((hit for hit in pattern_hits if hit.get("task_type") == preferred_task), None)
        if task_best and int(task_best.get("match_score", 0)) >= int(best.get("match_score", 0)) - 3:
            best = task_best

    method_family = str(best.get("method_family") or (chapter_hints[0] if chapter_hints else "unknown"))
    procedure = str(best.get("procedure") or (chapter_hints[1] if len(chapter_hints) > 1 else method_family))
    task_type = str(best.get("task_type") or (task_matches[0] if task_matches else "unknown"))
    parameter = str(best.get("parameter") or (parameter_matches[0] if parameter_matches else "unknown"))

    assumptions: List[str] = []
    for hit in pattern_hits:
        assumptions.extend(str(x) for x in hit.get("assumptions", []))

    token_counts = Counter(_tokens(text))
    return {
        "id": str(record.get("id", "")),
        "chapter": chapter,
        "method_family": method_family,
        "procedure": procedure,
        "task_type": task_type,
        "parameter": parameter,
        "assumptions": sorted(set(assumptions)),
        "formula_patterns": [str(hit["id"]) for hit in pattern_hits],
        "symbols": _symbols(text),
        "tokens": dict(token_counts),
    }


def feature_terms(features: Dict[str, Any]) -> Counter[str]:
    terms: Counter[str] = Counter()
    for token, count in features.get("tokens", {}).items():
        terms[f"tok:{token}"] += int(count)
    weighted_singletons = {
        "chapter": 5,
        "method_family": 8,
        "procedure": 10,
        "task_type": 7,
        "parameter": 7,
    }
    for key, weight in weighted_singletons.items():
        value = features.get(key)
        if value and value != "unknown":
            terms[f"{key}:{value}"] += weight
    for key, weight in (("formula_patterns", 12), ("assumptions", 5), ("symbols", 3)):
        for value in features.get(key, []) or []:
            terms[f"{key}:{value}"] += weight
    return terms


def iter_jsonl_records(input_path: Path) -> Iterable[Dict[str, Any]]:
    files = [input_path] if input_path.is_file() else sorted(input_path.glob("exercises_ch*.jsonl"))
    for path in files:
        if not re.search(r"exercises_ch(?:1[5-9]|2\d|30)\.jsonl$", path.name):
            continue
        with path.open("r", encoding="utf-8") as fh:
            for line_no, line in enumerate(fh, start=1):
                line = line.strip()
                if not line:
                    continue
                record = json.loads(line)
                record["_jsonl_path"] = path.as_posix()
                record["_jsonl_line"] = line_no
                yield record
