"""평가 하네스 러너 — 골든셋을 트랙에 통과시켜 검색·근거 지표를 채점한다.

원칙: 데이터셋(golden_set.yaml)과 채점(scoring.py)은 무쿼터·결정론.
실제 점수 산출만 트랙 호출(API/서비스)이 필요하다. 쿼터를 아끼려면 --retrieval-only.

사용:
  .venv/bin/python -m evaluation.run_eval --dry-run            # 골든셋 검증(무API)
  .venv/bin/python -m evaluation.run_eval --track vector        # vector만 채점
  .venv/bin/python -m evaluation.run_eval --retrieval-only      # 생성 생략(쿼터 절약)
  .venv/bin/python -m evaluation.run_eval --track all --limit 3 # 앞 3케이스만
  .venv/bin/python -m evaluation.run_eval --ids loki-viz-cause  # 특정 케이스만

주의: 실제 채점은 Neo4j/Qdrant 기동 + Gemini 쿼터가 필요하다. --retrieval-only는
'최종 답변 생성'만 건너뛴다 — graph/hybrid는 질문 엔티티 추출(find_question_entities →
extract_question_entities)에서 여전히 generate_content를 케이스당 1회 호출한다.
진짜로 생성 쿼터를 0으로 하려면 graph에 --no-llm-entities를 함께 쓰라(lexical 매칭으로 대체).
vector는 retrieval-only면 생성 호출이 없다(임베딩만). hybrid는 내부적으로 graph 엔티티
추출을 쓰므로 --no-llm-entities로도 완전히 0으로 만들 수 없다.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import yaml

from evaluation import scoring

HERE = Path(__file__).resolve().parent
GOLDEN_PATH = HERE / "golden_set.yaml"
REPORTS_DIR = HERE / "reports"
TRACKS = ["vector", "graph", "hybrid"]


def load_golden():
    return yaml.safe_load(GOLDEN_PATH.read_text(encoding="utf-8")) or []


def _unique(seq):
    out = []
    for x in seq:
        if x and x not in out:
            out.append(x)
    return out


# --- 트랙 어댑터: 질문 -> 정규화 출력. 무거운 import는 함수 안에서(드라이런 경량화) ---

def run_vector(question, retrieval_only, no_llm_entities=False):
    # vector는 엔티티 추출을 쓰지 않음 — no_llm_entities 무시(파라미터만 받음)
    from vector.query import create_retriever, generate_answer

    retriever = create_retriever()
    docs = retriever.invoke(question)
    return {
        "track": "vector",
        "question": question,
        "retrieved_sources": _unique(d.metadata.get("source_file") for d in docs),
        "matched_entities": [],
        "answer": None if retrieval_only else generate_answer(question, docs),
    }


def run_graph(question, retrieval_only, no_llm_entities=False):
    from neo4j import GraphDatabase
    from graph.query import (
        NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
        find_question_entities, find_question_entities_lexical,
        retrieve_graph_context, generate_answer,
    )

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    try:
        if no_llm_entities:
            entities = find_question_entities_lexical(driver, question)
        else:
            entities = find_question_entities(driver, question)
        rels = retrieve_graph_context(driver, [e["id"] for e in entities])
    finally:
        driver.close()
    return {
        "track": "graph",
        "question": question,
        "retrieved_sources": _unique(r.get("source_document") for r in rels),
        "matched_entities": [e["id"] for e in entities],
        "answer": None if retrieval_only else generate_answer(question, entities, rels),
    }


def run_hybrid(question, retrieval_only, no_llm_entities=False):
    # hybrid는 내부 retrieve_graph가 LLM 엔티티를 씀 — no_llm_entities 무시
    from hybrid.query import retrieve_vector, retrieve_graph, generate_hybrid_answer
    from vector.query import format_documents
    from graph.query import build_graph_context

    try:
        vector_docs = retrieve_vector(question)
    except Exception:
        vector_docs = []
    vector_context = format_documents(vector_docs)
    try:
        entities, rels = retrieve_graph(question, vector_context)
    except Exception:
        entities, rels = [], []
    sources = _unique(
        [d.metadata.get("source_file") for d in vector_docs]
        + [r.get("source_document") for r in rels]
    )
    answer = None if retrieval_only else generate_hybrid_answer(
        question, vector_context, build_graph_context(entities, rels)
    )
    return {
        "track": "hybrid",
        "question": question,
        "retrieved_sources": sources,
        "matched_entities": [e["id"] for e in entities],
        "answer": answer,
    }


ADAPTERS = {"vector": run_vector, "graph": run_graph, "hybrid": run_hybrid}


def dry_run(cases):
    print(f"골든셋 케이스 {len(cases)}개")
    ok = True
    for c in cases:
        missing = [k for k in ("id", "question") if not c.get(k)]
        if missing:
            ok = False
        tags = ",".join(c.get("tags", []))
        flag = "OK" if not missing else f"누락 {missing}"
        print(f"- {str(c.get('id', '?')):24} best={str(c.get('best_track', '?')):7} [{tags}] {flag}")
    print("\n검증:", "통과" if ok else "실패(필수 필드 누락)")
    return ok


def evaluate(cases, tracks, retrieval_only, no_llm_entities):
    rows = []
    for case in cases:
        for track in tracks:
            try:
                output = ADAPTERS[track](case["question"], retrieval_only, no_llm_entities)
                res = scoring.score_case(case, output, retrieval_only=retrieval_only)
                res["error"] = None
            except Exception as exc:  # 서비스/쿼터 실패는 케이스별로 격리
                res = {"id": case.get("id"), "track": track, "passed": None, "error": type(exc).__name__}
            rows.append(res)
    return rows


def _fmt(value):
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "O" if value else "X"
    return f"{value:.2f}"


def print_scorecard(rows):
    print(f"\n{'id':24} {'track':7} {'src':>5} {'ent':>5} {'kw':>5}  pass")
    print("-" * 56)
    for r in rows:
        if r.get("error"):
            print(f"{str(r.get('id')):24} {str(r.get('track')):7} ERROR: {r['error']}")
            continue
        print(
            f"{str(r.get('id')):24} {str(r.get('track')):7} "
            f"{_fmt(r.get('source_recall')):>5} {_fmt(r.get('entity_recall')):>5} "
            f"{_fmt(r.get('keyword_coverage')):>5}  {_fmt(r.get('passed'))}"
        )
    print("\n[트랙별 통과율]")
    for track in TRACKS:
        same = [r for r in rows if r.get("track") == track]
        if not same:
            continue
        scored = [r for r in same if r.get("passed") is not None]
        errored = [r for r in same if r.get("error")]
        passed = sum(1 for r in scored if r["passed"])
        extra = f"  (에러 {len(errored)})" if errored else ""
        print(f"- {track:7}: {passed}/{len(scored)}{extra}")


def parse_args():
    ap = argparse.ArgumentParser(description="RAG 3트랙 평가 하네스")
    ap.add_argument("--track", default="all", choices=["all"] + TRACKS)
    ap.add_argument("--retrieval-only", action="store_true", help="생성 생략(쿼터 절약)")
    ap.add_argument("--no-llm-entities", action="store_true", help="graph 엔티티추출을 LLM 대신 lexical로(생성 쿼터 0)")
    ap.add_argument("--limit", type=int, help="앞 N개 케이스만")
    ap.add_argument("--ids", help="쉼표로 구분한 케이스 id만")
    ap.add_argument("--dry-run", action="store_true", help="골든셋 검증만(무API)")
    return ap.parse_args()


def main():
    args = parse_args()
    cases = load_golden()
    if args.ids:
        want = {s.strip() for s in args.ids.split(",")}
        cases = [c for c in cases if c.get("id") in want]
    if args.limit:
        cases = cases[: args.limit]

    if args.dry_run:
        sys.exit(0 if dry_run(cases) else 1)

    tracks = TRACKS if args.track == "all" else [args.track]
    rows = evaluate(cases, tracks, args.retrieval_only, args.no_llm_entities)
    print_scorecard(rows)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    report = REPORTS_DIR / f"eval-{stamp}.json"
    report.write_text(
        json.dumps({"retrieval_only": args.retrieval_only, "rows": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\n리포트 저장: {report}")


if __name__ == "__main__":
    main()
