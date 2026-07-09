import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


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


def generate_answer(question, entities, relationships):
    if not entities:
        return "질문과 관련된 Entity를 찾지 못했습니다."

    if not relationships:
        return "관련 Entity는 찾았지만 연결된 관계를 찾지 못했습니다."

    lines = [
        "그래프 관계 기준 답변:",
        "",
    ]

    for relationship in relationships:
        lines.append(
            f"- {relationship['source']} --[{relationship['relation']}]--> "
            f"{relationship['target']}: {relationship['description']}"
        )

    lines.append("")
    lines.append("요약:")

    if "deployment" in question.lower() and "외부" in question:
        lines.append(
            "Deployment는 Pod와 연결되어 있고, Service-JS는 Pod를 외부 통신 가능하도록 열어준다. "
            "따라서 Deployment를 외부 통신하려면 Service-JS를 통해 Pod를 노출해야 한다."
        )
    else:
        lines.append("위 관계를 근거로 질문과 관련된 Entity 연결을 확인할 수 있다.")

    return "\n".join(lines)


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
