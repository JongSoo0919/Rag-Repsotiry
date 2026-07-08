import sys

import networkx as nx


# 1. 원본 문서 조각 준비
documents = {
    "회원 탈퇴": "회원은 언제든지 탈퇴할 수 있다. 탈퇴 시 개인정보는 제12조에 따라 처리한다.",
    "제6조": "회원의 탈퇴 조건과 절차를 정의한다.",
    "제12조": "회원의 개인정보는 관련 법령에 따라 보관 또는 파기한다.",
    "개인정보보호법 제21조": "개인정보 처리자는 보유기간 경과 또는 목적 달성 시 개인정보를 지체 없이 파기해야 한다.",
    "유료 서비스 해지" : "회원은 언제든지 본인이 원할 때 유료 서비스를 해지할 수 있다. 해지 시 서비스 중지는 제 10조에 따라 처리한다.",
    "제10조" : "유료 서비스가 해지되면 당일 날 서비스를 모두 중지한다.",
    "제20조" : "유료 서비스에 대한 정보는 관련 법령에 따라 보관 또는 파기한다.",
    "환불법 제5조" : "금액은 무조건 80%만 환불 된다."
}


# 2. 그래프 생성
graph = nx.DiGraph()


# 3. 노드 추가 - 탈퇴
graph.add_node("회원 탈퇴", type="concept", text=documents["회원 탈퇴"])
graph.add_node("제6조", type="term", text=documents["제6조"])
graph.add_node("제12조", type="term", text=documents["제12조"])
graph.add_node("개인정보보호법 제21조", type="law", text=documents["개인정보보호법 제21조"])

# 3. 노드 추가 - 환불
graph.add_node("유료 서비스 해지", type="concept", text=documents["유료 서비스 해지"])
graph.add_node("제10조", type="term", text=documents["제10조"])
graph.add_node("제20조", type="term", text=documents["제20조"])
graph.add_node("환불법 제5조", type="law", text=documents["환불법 제5조"])

# 4. 관계 추가 - 탈퇴
graph.add_edge("회원 탈퇴", "제6조", relation="defined_in")
graph.add_edge("회원 탈퇴", "제12조", relation="references")
graph.add_edge("제12조", "개인정보보호법 제21조", relation="based_on")

# 4. 관계 추가 - 환불
graph.add_edge("유료 서비스 해지", "제10조", relation="defined_in")
graph.add_edge("유료 서비스 해지", "제20조", relation="references")
graph.add_edge("제10조", "환불법 제5조", relation="based_on")

def find_start_node(question: str):
    """질문에 포함된 키워드로 시작 노드를 찾는다."""
    for node in graph.nodes:
        if node in question:
            return node

    aliases = {
        "탈퇴": "회원 탈퇴",
        "개인정보": "제12조",
        "파기": "개인정보보호법 제21조",
    }

    for keyword, node in aliases.items():
        if keyword in question:
            return node

    return None


def retrieve_graph_context(start_node: str, depth: int = 2):
    """시작 노드부터 관계를 따라가며 관련 노드와 엣지를 수집한다."""
    visited = set()
    contexts = []
    edges = []

    def dfs(node, current_depth):
        if current_depth > depth or node in visited:
            return

        visited.add(node)
        node_data = graph.nodes[node]
        contexts.append(
            {
                "node": node,
                "type": node_data.get("type"),
                "text": node_data.get("text"),
            }
        )

        for next_node in graph.successors(node):
            relation = graph.edges[node, next_node].get("relation")
            edges.append(
                {
                    "from": node,
                    "to": next_node,
                    "relation": relation,
                }
            )
            dfs(next_node, current_depth + 1)

    dfs(start_node, 0)
    return contexts, edges


def answer_without_llm(question: str):
    """LLM 없이 그래프 탐색 결과만으로 단순 답변을 만든다."""
    start_node = find_start_node(question)

    if not start_node:
        return {
            "answer": "질문과 관련된 시작 노드를 찾지 못했습니다.",
            "contexts": [],
            "edges": [],
        }

    contexts, edges = retrieve_graph_context(start_node)

    lines = [
        f"질문과 가장 가까운 시작 노드는 '{start_node}'입니다.",
        "",
        "관련 근거:",
    ]

    for context in contexts:
        lines.append(f"- {context['node']} ({context['type']}): {context['text']}")

    lines.append("")
    lines.append("관계:")

    for edge in edges:
        lines.append(f"- {edge['from']} --[{edge['relation']}]--> {edge['to']}")

    return {
        "answer": "\n".join(lines),
        "contexts": contexts,
        "edges": edges,
    }


def print_graph():
    print("그래프 관계")
    print("=" * 80)
    for from_node, to_node, data in graph.edges(data=True):
        print(f"{from_node} --[{data['relation']}]--> {to_node}")
    print()


def main():
    question = " ".join(sys.argv[1:]).strip()

    # if not question:
    #     question = "회원 탈퇴 시 개인정보는 어떻게 처리돼?"

    if not question:
        question = "유료 서비스 해지 시 결제 금액은 어떻게 돼?"

    print_graph()
    result = answer_without_llm(question)

    print(f"질문: {question}")
    print("=" * 80)
    print(result["answer"])


if __name__ == "__main__":
    main()
