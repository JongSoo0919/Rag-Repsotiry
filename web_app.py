"""통합 웹앱 — Vector / Graph / Hybrid 질의 + Graph 탐색을 탭 하나로.

하나만 켜면 탭 전환으로 3트랙 질의 + 지식그래프 탐색을 확인한다:
    QDRANT_COLLECTION=rag_poc_chunks_gemini .venv/bin/uvicorn web_app:app --port 8000
    -> http://localhost:8000

- 질의 탭(hybrid/vector/graph): 질문 → RAG 답변 + 근거 (Gemini 필요)
- 탐색 탭(explore): Neo4j 지식그래프를 vis-network로 시각화 (LLM 불필요, 무쿼터)

주의: 내부 PoC용. 인증·레이트리밋 없음 → 127.0.0.1 바인딩 권장.
      탐색 탭은 vis-network를 CDN에서 로드하므로 인터넷 필요.
"""
import html
import json
import logging

from fastapi import FastAPI, Form
from fastapi.responses import HTMLResponse

app = FastAPI(title="RAG 3트랙 + 그래프 탐색")

MAX_Q = 2000  # 질문 길이 상한(비용·DoS 방지)
QUERY_TRACKS = ["hybrid", "vector", "graph"]
TABS = QUERY_TRACKS + ["explore"]
TAB_LABEL = {
    "hybrid": "Hybrid (벡터+그래프)",
    "vector": "Vector (문서 서술)",
    "graph": "Graph (관계 중심)",
    "explore": "Graph 탐색",
}
EXAMPLES = {
    "hybrid": [
        "Loki 로그는 어디에 저장되고 보관 기간과 삭제는 어떻게 동작해?",
        "Thanos Compactor는 왜 하나만 배포해야 하고 보관 주기는 어떻게 돼?",
    ],
    "vector": [
        "Biz 클러스터 MinIO PV 권장 크기와 산정 공식이 뭐야?",
        "node-exporter 경량화는 어떻게 설정해?",
    ],
    "graph": [
        "Monitoring HA 컴포넌트는 어느 노드에 배치되고 무엇이 있어?",
        "Thanos는 Prometheus의 어떤 한계를 해결해?",
    ],
}

_DRIVER = None


def _driver():
    """Neo4j 드라이버 모듈 싱글턴(요청마다 새 풀 생성 방지)."""
    global _DRIVER
    if _DRIVER is None:
        from neo4j import GraphDatabase
        from graph.query import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD
        _DRIVER = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _DRIVER


# ---------- 트랙 실행 (질의) ----------

def run_vector(question):
    from vector.query import create_retriever, generate_answer
    docs = create_retriever().invoke(question)
    answer = generate_answer(question, docs)
    ev = [f"문서: {d.metadata.get('source_file', '?')}  ·  section: {d.metadata.get('section', '?')}" for d in docs]
    return answer, "검색 청크", ev


def run_graph(question):
    from graph.query import find_question_entities, retrieve_graph_context, generate_answer
    driver = _driver()
    entities = find_question_entities(driver, question)
    rels = retrieve_graph_context(driver, [e["id"] for e in entities])
    answer = generate_answer(question, entities, rels)
    ev = [f"엔티티: {', '.join(e['id'] for e in entities) or '없음'}"]
    ev += [f"{r.get('source')} -[{r.get('relation')}]-> {r.get('target')}" for r in rels[:10]]
    return answer, "그래프 근거", ev


def run_hybrid(question):
    from hybrid.query import hybrid_answer
    vector_docs, entities, rels, answer = hybrid_answer(question)
    ev = [f"벡터 청크: {', '.join(d.metadata.get('section', '?') for d in vector_docs) or '없음'}"]
    ev.append(f"그래프 시드 엔티티: {', '.join(e['id'] for e in entities) or '없음'}")
    ev += [f"{r.get('source')} -[{r.get('relation')}]-> {r.get('target')}" for r in rels[:8]]
    return answer, "종합 근거", ev


RUNNERS = {"vector": run_vector, "graph": run_graph, "hybrid": run_hybrid}


# ---------- 그래프 탐색 데이터 ----------

def fetch_graph(limit_nodes=250):
    driver = _driver()
    with driver.session() as s:
        nodes = [r.data() for r in s.run(
            "MATCH (e:Entity) WHERE e.tutorial = true "
            "OPTIONAL MATCH (e)-[r]-() WHERE type(r) <> 'MENTIONS' "
            "RETURN e.id AS id, e.type AS type, e.description AS description, count(r) AS deg "
            "ORDER BY deg DESC LIMIT $lim", lim=limit_nodes)]
        ids = {n["id"] for n in nodes}
        edges = [r.data() for r in s.run(
            "MATCH (a:Entity)-[r]->(b:Entity) "
            "WHERE r.tutorial = true AND type(r) <> 'MENTIONS' "
            "RETURN a.id AS source, type(r) AS rel, b.id AS target")]
    edges = [e for e in edges if e["source"] in ids and e["target"] in ids]
    return nodes, edges


# ---------- 렌더 ----------

STYLE = """
 body{font-family:-apple-system,system-ui,sans-serif;max-width:900px;margin:24px auto;padding:0 16px;color:#1a1a1a}
 h1{font-size:20px}
 .tabs{display:flex;gap:4px;border-bottom:2px solid #e5e5e5;margin:16px 0;flex-wrap:wrap}
 .tab{padding:10px 16px;text-decoration:none;color:#555;border:1px solid transparent;border-bottom:none;border-radius:8px 8px 0 0}
 .tab.active{background:#f3f4f6;color:#111;font-weight:600;border-color:#e5e5e5}
 textarea{width:100%;height:70px;padding:10px;font-size:15px;border:1px solid #ccc;border-radius:8px;box-sizing:border-box}
 .chip{margin:6px 6px 0 0;padding:6px 10px;font-size:13px;border:1px solid #ddd;border-radius:14px;background:#fafafa;cursor:pointer}
 button.go{margin-top:10px;padding:10px 20px;font-size:15px;background:#111;color:#fff;border:0;border-radius:8px;cursor:pointer}
 .ans{white-space:pre-wrap;background:#f7f9fc;border:1px solid #e5eaf2;border-radius:10px;padding:16px;margin-top:18px;line-height:1.6}
 .ev{margin-top:12px;font-size:13px;color:#555} .ev ul{margin:6px 0 0 18px}
 .err{margin-top:18px;color:#b00;background:#fff2f2;border:1px solid #f3c2c2;border-radius:8px;padding:12px}
 .hint{font-size:12px;color:#888;margin-top:6px}
"""


def _shell(active, inner):
    tabs = "".join(
        f'<a class="tab {"active" if t == active else ""}" href="/?track={t}">{html.escape(TAB_LABEL[t])}</a>'
        for t in TABS
    )
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        "<title>RAG 3트랙 + 그래프 탐색</title>"
        f"<style>{STYLE}</style></head><body>"
        "<h1>RAG 3트랙 + 그래프 탐색</h1>"
        f'<div class="tabs">{tabs}</div>{inner}</body></html>'
    )


def render_query(track, question="", answer="", ev_label="", evidence=None, error=""):
    if track not in QUERY_TRACKS:
        track = "hybrid"
    chips = "".join(
        f'<button type="button" class="chip" onclick="q.value=this.textContent">{html.escape(x)}</button>'
        for x in EXAMPLES[track]
    )
    result = ""
    if error:
        result = f'<div class="err">오류: {html.escape(error)}</div>'
    elif answer:
        ev_html = ""
        if evidence:
            items = "".join(f"<li>{html.escape(str(e))}</li>" for e in evidence)
            ev_html = f'<div class="ev"><b>{html.escape(ev_label)}</b><ul>{items}</ul></div>'
        result = f'<div class="ans">{html.escape(answer)}</div>{ev_html}'
    inner = (
        '<form method="post" action="/ask">'
        f'<input type="hidden" name="track" value="{html.escape(track)}">'
        f'<textarea id="q" name="question" placeholder="{html.escape(TAB_LABEL[track])} 트랙에 질문...">{html.escape(question)}</textarea>'
        f"<div>{chips}</div>"
        '<div class="hint">예시를 누르면 입력창에 채워집니다.</div>'
        '<button class="go" type="submit">질문</button>'
        f"</form>{result}"
    )
    return _shell(track, inner)


def render_explore():
    try:
        nodes, edges = fetch_graph()
    except Exception:
        logging.exception("graph fetch failed")
        return _shell("explore", '<div class="err">그래프를 불러오지 못했습니다 (Neo4j 확인).</div>')

    vis_nodes = [
        {"id": n["id"], "label": n["id"], "group": n.get("type") or "기타",
         "value": (n.get("deg") or 1), "desc": (n.get("description") or "")}
        for n in nodes
    ]
    vis_edges = [{"from": e["source"], "to": e["target"], "label": e["rel"]} for e in edges]
    nj = json.dumps(vis_nodes, ensure_ascii=False).replace("</", "<\\/")
    ej = json.dumps(vis_edges, ensure_ascii=False).replace("</", "<\\/")

    inner = (
        f'<p class="hint">엔티티 {len(nodes)} · 관계 {len(edges)}. 드래그·줌 가능, 노드 클릭 시 아래에 엔티티 내용 표시.</p>'
        '<div id="net" style="height:540px;border:1px solid #e5e5e5;border-radius:10px;background:#fff"></div>'
        '<div id="detail" style="margin-top:12px;padding:12px;background:#f7f9fc;border:1px solid #e5eaf2;border-radius:8px;font-size:14px">노드를 클릭하면 엔티티 내용이 표시됩니다.</div>'
        '<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>'
        "<script>"
        f"var NODES={nj};var EDGES={ej};"
        "var nodes=new vis.DataSet(NODES);var edges=new vis.DataSet(EDGES);"
        'var net=new vis.Network(document.getElementById("net"),{nodes:nodes,edges:edges},'
        '{nodes:{shape:"dot",scaling:{min:6,max:30},font:{size:12}},'
        'edges:{arrows:"to",font:{size:9,align:"middle",color:"#999"},color:{color:"#ccc"},smooth:{type:"continuous"}},'
        "physics:{stabilization:true,barnesHut:{gravitationalConstant:-5000,springLength:130,springConstant:0.03}}});"
        'net.on("click",function(p){var d=document.getElementById("detail");'
        "if(p.nodes.length){var n=nodes.get(p.nodes[0]);"
        'd.textContent="["+(n.group||"")+"]  "+n.id+"  —  "+(n.desc||"(설명 없음)");}'
        'else{d.textContent="노드를 클릭하면 엔티티 내용이 표시됩니다.";}});'
        "</script>"
    )
    return _shell("explore", inner)


@app.get("/", response_class=HTMLResponse)
def home(track: str = "hybrid"):
    if track == "explore":
        return render_explore()
    return render_query(track)


@app.post("/ask", response_class=HTMLResponse)
def ask(track: str = Form("hybrid"), question: str = Form("")):
    question = (question or "").strip()[:MAX_Q]
    if not question:
        return render_query(track, error="질문이 비어 있습니다.")
    try:
        answer, ev_label, evidence = RUNNERS.get(track, run_hybrid)(question)
        return render_query(track, question=question, answer=answer, ev_label=ev_label, evidence=evidence)
    except Exception:
        logging.exception("ask failed")
        return render_query(track, question=question, error="처리 중 오류가 발생했습니다.")
