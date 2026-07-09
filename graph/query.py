import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from neo4j import GraphDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")

LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("EMBEDDING_API_KEY")
LLM_API_MODEL = os.getenv("LLM_API_MODEL", "gemini-2.5-flash")


def find_question_entities(driver, question, limit=3):
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

    with driver.session() as session:
        return [record.data() for record in session.run(query, question=question, limit=limit)]


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
