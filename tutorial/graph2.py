import json
import os
import re
import sys
from pathlib import Path

import networkx as nx
from dotenv import load_dotenv
from google import genai


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("EMBEDDING_API_KEY")
LLM_API_MODEL = os.getenv("LLM_API_MODEL", "gemini-2.5-flash")


# 1. 원본 문서 조각 준비
# graph.py는 사람이 Node/Edge를 직접 작성했다.
# graph2.py는 LLM이 아래 문서를 읽고 Node/Edge 후보를 자동 추출한다.
#
# 질문 방법:
# - 실행 후 콘솔에 질문을 입력하거나,
# - 아래처럼 실행 인자로 질문을 넘긴다.
#   .venv/bin/python tutorial/graph2.py "Deployment를 외부 통신하려면 어떻게 해야해?"
documents = {
    "pod-basic": """
    Pod는 Kubernetes의 최소 배포 단위이다.
    Pod는 하나 이상의 컨테이너를 포함한다.
    """,
    "deployment-basic": """
    Deployment는 Pod를 관리할 수 있다.
    Deployment는 원하는 Pod 개수를 유지하고, Pod의 배포와 업데이트를 관리한다.
    """,
    "service-basic": """
    Service는 Pod를 외부 통신 가능하도록 열어준다.
    Service는 Pod 앞에서 고정된 접근 지점을 제공한다.
    """,
}


def build_extraction_prompt():
    document_text = "\n\n".join(
        f"[문서 ID: {document_id}]\n{content.strip()}"
        for document_id, content in documents.items()
    )

    return f"""
너는 문서를 읽고 Knowledge Graph의 Node와 Edge를 추출하는 assistant다.

규칙:
- 반드시 JSON만 출력한다.
- markdown code fence를 쓰지 않는다.
- nodes는 문서에서 중요한 개념, 기술, 리소스, 기능만 뽑는다.
- edges는 두 node 사이의 의미 있는 관계만 뽑는다.
- edge의 source와 target은 반드시 nodes에 존재하는 id를 사용한다.
- relation은 영문 snake_case로 작성한다.
- confidence는 0.0부터 1.0 사이 숫자로 작성한다.

JSON 형식:
{{
  "nodes": [
    {{
      "id": "Deployment",
      "type": "resource",
      "description": "Pod를 관리하는 Kubernetes 리소스",
      "source_document": "deployment-basic"
    }}
  ],
  "edges": [
    {{
      "source": "Deployment",
      "target": "Pod",
      "relation": "manages",
      "description": "Deployment는 Pod를 관리한다",
      "confidence": 0.95,
      "source_document": "deployment-basic"
    }}
  ]
}}

문서:
{document_text}
""".strip()


def extract_json(text):
    """LLM 응답에서 JSON 객체만 꺼낸다."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1:
        raise RuntimeError(f"LLM 응답에서 JSON을 찾지 못했습니다.\n응답:\n{text}")

    return json.loads(cleaned[start : end + 1])


def extract_graph_data_with_llm():
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY 또는 EMBEDDING_API_KEY를 설정해주세요.")

    client = genai.Client(api_key=LLM_API_KEY)
    response = client.models.generate_content(
        model=LLM_API_MODEL,
        contents=build_extraction_prompt(),
    )

    return extract_json(response.text)


def build_graph(graph_data):
    graph = nx.DiGraph()

    for node in graph_data.get("nodes", []):
        node_id = node["id"]
        graph.add_node(
            node_id,
            type=node.get("type", "concept"),
            description=node.get("description", ""),
            source_document=node.get("source_document", ""),
        )

    for edge in graph_data.get("edges", []):
        source = edge["source"]
        target = edge["target"]

        if source not in graph or target not in graph:
            continue

        graph.add_edge(
            source,
            target,
            relation=edge.get("relation", "related_to"),
            description=edge.get("description", ""),
            confidence=edge.get("confidence", 0.0),
            source_document=edge.get("source_document", ""),
        )

    return graph


def tokenize(text):
    return [token for token in re.split(r"[\s,./?]+", text.lower()) if token]


def find_question_nodes(graph, question, limit=3):
    """질문과 관련 있어 보이는 노드를 여러 개 찾는다."""
    question_lower = question.lower()
    question_tokens = tokenize(question)
    scored_nodes = []

    for node, data in graph.nodes(data=True):
        text = f"{node} {data.get('description', '')}".lower()
        score = 0

        if node.lower() in question_lower:
            score += 5

        for token in question_tokens:
            if token in text:
                score += 1

        if score > 0:
            scored_nodes.append((score, node))

    scored_nodes.sort(reverse=True)
    return [node for _, node in scored_nodes[:limit]]


def retrieve_graph_context(graph, seed_nodes, depth=2):
    """질문 관련 노드 주변을 양방향으로 탐색해 답변 근거를 모은다."""
    if not seed_nodes:
        return [], []

    undirected = graph.to_undirected()
    selected_nodes = set(seed_nodes)

    for seed_node in seed_nodes:
        lengths = nx.single_source_shortest_path_length(
            undirected,
            seed_node,
            cutoff=depth,
        )
        selected_nodes.update(lengths.keys())

    contexts = []
    for node in selected_nodes:
        node_data = graph.nodes[node]
        contexts.append(
            {
                "node": node,
                "type": node_data.get("type"),
                "description": node_data.get("description"),
                "source_document": node_data.get("source_document"),
            }
        )

    edges = []
    for source, target, edge_data in graph.edges(data=True):
        if source in selected_nodes and target in selected_nodes:
            edges.append(
                {
                    "from": source,
                    "to": target,
                    "relation": edge_data.get("relation"),
                    "description": edge_data.get("description"),
                    "confidence": edge_data.get("confidence"),
                    "source_document": edge_data.get("source_document"),
                }
            )

    return contexts, edges


def format_graph_context(contexts, edges):
    lines = ["[관련 노드]"]

    for context in contexts:
        lines.append(
            f"- {context['node']} ({context['type']}): "
            f"{context['description']} "
            f"[source={context['source_document']}]"
        )

    lines.append("")
    lines.append("[관련 관계]")

    for edge in edges:
        lines.append(
            f"- {edge['from']} --[{edge['relation']}]--> {edge['to']}: "
            f"{edge['description']} "
            f"[confidence={edge['confidence']}, source={edge['source_document']}]"
        )

    return "\n".join(lines)


def generate_answer_with_llm(question, contexts, edges):
    """추출된 그래프 근거만 사용해 질문에 대한 자연어 답변을 만든다."""
    if not contexts:
        return "질문과 관련된 그래프 노드를 찾지 못했습니다."

    client = genai.Client(api_key=LLM_API_KEY)
    graph_context = format_graph_context(contexts, edges)

    prompt = f"""
너는 Knowledge Graph 기반 질의응답 assistant다.

규칙:
- 아래 그래프 context에 있는 노드와 관계만 근거로 답변한다.
- 그래프 context에 없는 내용은 추측하지 않는다.
- 질문에 직접 답한다.
- 답변은 한국어로 짧고 명확하게 작성한다.

질문:
{question}

그래프 context:
{graph_context}
""".strip()

    response = client.models.generate_content(
        model=LLM_API_MODEL,
        contents=prompt,
    )
    return response.text


def print_graph(graph):
    print("LLM이 추출한 그래프")
    print("=" * 80)
    print(f"nodes: {graph.number_of_nodes()}")
    print(f"edges: {graph.number_of_edges()}")
    print()

    for source, target, data in graph.edges(data=True):
        print(f"{source} --[{data['relation']}]--> {target}")
    print()


def main():
    question = " ".join(sys.argv[1:]).strip()

    if not question:
        question = input("질문을 입력하세요: ").strip()

    if not question:
        question = "Deployment를 외부 통신하려면 어떻게 해야해?"

    graph_data = extract_graph_data_with_llm()
    graph = build_graph(graph_data)
    seed_nodes = find_question_nodes(graph, question)
    contexts, edges = retrieve_graph_context(graph, seed_nodes)
    answer = generate_answer_with_llm(question, contexts, edges)

    print_graph(graph)
    print(f"질문: {question}")
    print("=" * 80)
    print(f"질문 관련 시작 노드: {', '.join(seed_nodes) if seed_nodes else '(없음)'}")
    print()
    print("그래프 근거")
    print("-" * 80)
    print(format_graph_context(contexts, edges))
    print()
    print("답변")
    print("-" * 80)
    print(answer)


if __name__ == "__main__":
    main()
