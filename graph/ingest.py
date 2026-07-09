import os
import re
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

from graph.documents import extract_graph_data_with_llm
from graph.embedding import create_embedding


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")


def normalize_relation_name(relation):
    """Neo4j relationship type은 영문 대문자/숫자/underscore 형태로 맞춘다."""
    normalized = re.sub(r"[^0-9a-zA-Z_]", "_", relation or "related_to")
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized.upper() or "RELATED_TO"


def test_connection(driver):
    with driver.session() as session:
        result = session.run("RETURN 1 AS ok")
        return result.single()["ok"] == 1


def create_constraints(driver):
    with driver.session() as session:
        session.run(
            """
            CREATE CONSTRAINT entity_id IF NOT EXISTS
            FOR (e:Entity)
            REQUIRE e.id IS UNIQUE
            """
        )
        session.run(
            """
            CREATE CONSTRAINT source_document_id IF NOT EXISTS
            FOR (s:SourceDocument)
            REQUIRE s.id IS UNIQUE
            """
        )


def clear_tutorial_graph(driver):
    with driver.session() as session:
        session.run(
            """
            MATCH (n)
            WHERE n.tutorial = true
            DETACH DELETE n
            """
        )


def enrich_nodes_with_embeddings(nodes):
    enriched = []
    for node in nodes:
        text = f"{node['id']}. {node.get('description', '')}"
        enriched.append({**node, "embedding": create_embedding(text)})
    return enriched


def upsert_nodes(driver, enriched_nodes):
    query = """
    UNWIND $nodes AS node
    MERGE (e:Entity {id: node.id})
    SET e.name = node.id,
        e.type = node.type,
        e.description = node.description,
        e.source_document = node.source_document,
        e.embedding = node.embedding,
        e.tutorial = true
    MERGE (s:SourceDocument {id: node.source_document})
    SET s.tutorial = true
    MERGE (s)-[:MENTIONS]->(e)
    """
    with driver.session() as session:
        session.run(query, nodes=enriched_nodes)


def upsert_edges(driver, edges):
    with driver.session() as session:
        for edge in edges:
            relation = normalize_relation_name(edge.get("relation"))
            query = f"""
            MATCH (source:Entity {{id: $source}})
            MATCH (target:Entity {{id: $target}})
            MERGE (source)-[r:{relation}]->(target)
            SET r.description = $description,
                r.confidence = $confidence,
                r.source_document = $source_document,
                r.tutorial = true
            """
            session.run(
                query,
                source=edge["source"],
                target=edge["target"],
                description=edge.get("description", ""),
                confidence=float(edge.get("confidence", 0.0)),
                source_document=edge.get("source_document", ""),
            )


def print_summary(driver):
    with driver.session() as session:
        counts = session.run(
            """
            MATCH (n)
            WHERE n.tutorial = true
            WITH count(n) AS node_count
            OPTIONAL MATCH ()-[r]->()
            WHERE r.tutorial = true
            RETURN node_count, count(r) AS edge_count
            """
        ).single()

        print(f"Neo4j 저장 완료: nodes={counts['node_count']}, edges={counts['edge_count']}")
        print()
        print("Neo4j Browser에서 확인할 Cypher:")
        print("MATCH (n)-[r]->(m) WHERE n.tutorial = true RETURN n, r, m")
        print()
        print("Deployment 주변 관계:")
        print('MATCH path = (d:Entity {id: "Deployment"})-[*1..2]-(n) RETURN path')


def load_graph_data():
    return extract_graph_data_with_llm()


def main():
    graph_data = load_graph_data()
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    driver = GraphDatabase.driver(
        NEO4J_URI,
        auth=(NEO4J_USER, NEO4J_PASSWORD),
    )

    try:
        if not test_connection(driver):
            raise RuntimeError("Neo4j 연결 테스트에 실패했습니다.")

        create_constraints(driver)
        enriched_nodes = enrich_nodes_with_embeddings(nodes)  # 임베딩 먼저(실패해도 clear 전)
        clear_tutorial_graph(driver)                          # 성공 후에만 삭제
        upsert_nodes(driver, enriched_nodes)
        upsert_edges(driver, edges)
        print_summary(driver)
    finally:
        driver.close()


if __name__ == "__main__":
    main()
