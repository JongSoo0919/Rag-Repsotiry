import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from neo4j import GraphDatabase

from graph.documents import extract_json
from graph.embedding import create_embedding
from preprocessing.aliases import normalize as normalize_entity
from preprocessing.aliases import build_alias_map


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("EMBEDDING_API_KEY")
LLM_API_MODEL = os.getenv("LLM_API_MODEL", "gemini-2.5-flash")

ENTITY_MATCH_THRESHOLD = float(os.getenv("GRAPH_ENTITY_MATCH_THRESHOLD", "0.5"))


def extract_question_entities(question):
    """질문에서 그래프 탐색 시작점이 될 엔티티(개념/고유명사) 후보를 뽑는다."""
    if not LLM_API_KEY:
        return []
    client = genai.Client(api_key=LLM_API_KEY)
    prompt = f'''
너는 질문에서 Knowledge Graph 탐색의 시작점이 될 엔티티(개념/고유명사/시스템/리소스)를 뽑는 assistant다.
규칙:
- 반드시 JSON만 출력한다. markdown code fence 금지.
- 질문에 실제로 등장하거나 강하게 함의된 핵심 엔티티만 뽑는다.
- 질문을 최우선 기준으로 삼고, 함께 제공되는 문서 맥락이 있으면 질문과 직접 관련된 엔티티를 고르는 보조 힌트로만 사용한다.
- 형식: {{"entities": ["엔티티1", "엔티티2"]}}

질문:
{question}
'''.strip()
    response = client.models.generate_content(model=LLM_API_MODEL, contents=prompt)
    if not response.text:
        return []
    data = extract_json(response.text)
    entities = data.get("entities", [])
    if not isinstance(entities, list):
        return []
    return [e for e in entities if isinstance(e, str) and e.strip()]


def cosine_similarity(vec_a, vec_b):
    if len(vec_a) != len(vec_b):
        return 0.0  # 임베딩 차원 불일치는 매칭 실패로 처리(침묵 오류 방지)
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def fetch_entity_embeddings(driver):
    query = """
    MATCH (e:Entity)
    WHERE e.tutorial = true AND e.embedding IS NOT NULL
    RETURN e.id AS id, e.description AS description, e.embedding AS embedding
    """
    with driver.session() as session:
        return [record.data() for record in session.run(query)]


def match_entities_to_nodes(driver, question_entities, limit=3):
    """추출된 엔티티 각각을 노드 임베딩과 코사인 비교해 매칭되는 노드를 고른다."""
    nodes = fetch_entity_embeddings(driver)
    if not nodes:
        return []
    best = {}  # node_id -> (score, description)
    for phrase in question_entities:
        phrase_vec = create_embedding(phrase)
        scored = sorted(
            ((cosine_similarity(phrase_vec, n["embedding"]), n) for n in nodes),
            key=lambda item: item[0],
            reverse=True,
        )
        for score, n in scored[:limit]:
            if score < ENTITY_MATCH_THRESHOLD:
                continue
            if n["id"] not in best or score > best[n["id"]][0]:
                best[n["id"]] = (score, n["description"])
    ranked = sorted(best.items(), key=lambda item: item[1][0], reverse=True)
    return [{"id": node_id, "description": desc} for node_id, (score, desc) in ranked[:limit]]


def find_question_entities(driver, question, limit=3, fallback_question=None):
    """질문 → LLM 엔티티 추출 → 노드 임베딩 매칭. 실패 시 CONTAINS로 fallback.
    fallback_question: lexical fallback에 쓸 텍스트(기본은 question). 하이브리드에서
    추출엔 '질문+문서맥락'을, fallback엔 '원 질문'만 쓰도록 분리하는 용도."""
    try:
        # 질문에서 뽑은 표기도 사전 기준으로 통일(예: "k8s" -> "Kubernetes")해 노드와 매칭
        question_entities = [normalize_entity(e) for e in extract_question_entities(question)]
        if question_entities:
            matched = match_entities_to_nodes(driver, question_entities, limit=limit)
            if matched:
                return matched
    except Exception:
        # LLM/임베딩/파싱 실패 → lexical fallback으로 저하 동작
        pass
    return find_question_entities_lexical(driver, fallback_question or question, limit=limit)


def _expand_with_aliases(question):
    """질문에 별칭(k8s 등)이 들어있으면 정식명칭(Kubernetes)을 덧붙여,
    canonical로 저장된 노드도 lexical 매칭되게 한다."""
    lowered = question.lower()
    extras = sorted({canonical for alias, canonical in build_alias_map().items() if alias in lowered})
    return question + " " + " ".join(extras) if extras else question


def find_question_entities_lexical(driver, question, limit=3):
    query = """
    MATCH (e:Entity)
    WHERE e.tutorial = true
      AND (
        toLower($question) CONTAINS toLower(e.id)
        OR toLower(e.description) CONTAINS toLower($question)
        OR any(token IN split(toLower($question), " ")
               WHERE token <> "" AND toLower(e.description) CONTAINS token)
      )
    RETURN e.id AS id, e.description AS description
    LIMIT $limit
    """

    expanded = _expand_with_aliases(question)
    with driver.session() as session:
        return [record.data() for record in session.run(query, question=expanded, limit=limit)]


def retrieve_graph_context(driver, entity_ids, depth=2):
    if not entity_ids:
        return []

    query = """
    MATCH path = (start:Entity)-[*1..2]-(related)
    WHERE start.id IN $entity_ids
      AND start.tutorial = true
    UNWIND relationships(path) AS r
    WITH DISTINCT r
    WHERE type(r) <> "MENTIONS"
    RETURN startNode(r).id AS source,
           type(r) AS relation,
           endNode(r).id AS target,
           r.description AS description,
           r.source_document AS source_document
    LIMIT 20
    """

    rows = []

    with driver.session() as session:
        for record in session.run(query, entity_ids=entity_ids, depth=depth):
            rows.append(
                {
                    "source": record["source"],
                    "relation": record["relation"],
                    "target": record["target"],
                    "description": record["description"] or "",
                    "source_document": record["source_document"] or "",
                }
            )

    return deduplicate_rows(rows)


def deduplicate_rows(rows):
    seen = set()
    result = []

    for row in rows:
        key = (row["source"], row["relation"], row["target"])

        if key in seen:
            continue

        seen.add(key)
        result.append(row)

    return result


def build_graph_context(entities, relationships):
    """탐색한 Entity/관계를 LLM에 넣을 context 문자열로 만든다."""
    lines = ["[관련 Entity]"]

    for entity in entities:
        description = entity.get("description") or ""
        lines.append(f"- {entity['id']}: {description}")

    lines.append("")
    lines.append("[관련 관계]")

    for relationship in relationships:
        lines.append(
            f"- {relationship['source']} --[{relationship['relation']}]--> "
            f"{relationship['target']}: {relationship['description']} "
            f"[source={relationship['source_document']}]"
        )

    return "\n".join(lines)


def format_relationships_only(relationships):
    """LLM 없이 그래프 관계만 나열하는 fallback 출력."""
    lines = ["그래프 관계 기준 답변:", ""]

    for relationship in relationships:
        lines.append(
            f"- {relationship['source']} --[{relationship['relation']}]--> "
            f"{relationship['target']}: {relationship['description']}"
        )

    return "\n".join(lines)


def generate_answer(question, entities, relationships):
    if not entities:
        return "질문과 관련된 Entity를 찾지 못했습니다."

    if not relationships:
        return "관련 Entity는 찾았지만 연결된 관계를 찾지 못했습니다."

    context = build_graph_context(entities, relationships)

    # LLM 키가 없으면 그래프 관계만 나열해 최소 동작을 보장한다.
    if not LLM_API_KEY:
        return format_relationships_only(relationships)

    client = genai.Client(api_key=LLM_API_KEY)

    prompt = f"""
너는 Knowledge Graph 기반 질의응답 assistant다.

규칙:
- 아래 그래프 context(Entity와 관계)만 근거로 답변한다.
- context에 없는 내용은 "그래프에서 확인할 수 없습니다."라고 답변한다.
- Entity 사이의 관계 경로를 따라가며 논리적으로 설명한다.
- 답변은 한국어로 작성한다.
- 답변 마지막에 근거로 사용한 관계를 bullet로 표시한다.

질문:
{question}

그래프 context:
{context}
""".strip()

    response = client.models.generate_content(
        model=LLM_API_MODEL,
        contents=prompt,
    )

    if not response.text:
        return format_relationships_only(relationships)

    return response.text


def main():
    question = " ".join(sys.argv[1:]).strip()

    if not question:
        question = input("질문을 입력하세요: ").strip()

    if not question:
        question = "Deployment를 외부 통신하려면 어떻게 해야해?"

    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )

    try:
        entities = find_question_entities(driver, question)
        relationships = retrieve_graph_context(driver, [entity["id"] for entity in entities])
        answer = generate_answer(question, entities, relationships)

        print(f"질문: {question}")
        print()
        print("관련 Entity:")
        for entity in entities:
            print(f"- {entity['id']}: {entity['description']}")
        print()
        print(answer)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
