import sys

from neo4j import GraphDatabase
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI

from vector.query import create_retriever, format_documents, LLM_API_KEY, LLM_API_MODEL
from graph.query import (
    NEO4J_URI,
    NEO4J_USER,
    NEO4J_PASSWORD,
    find_question_entities,
    retrieve_graph_context,
    build_graph_context,
)


def retrieve_vector(question):
    """① Vector: 의미 유사 청크 검색."""
    retriever = create_retriever()
    return retriever.invoke(question)


def retrieve_graph(question, vector_context):
    """② Bridge: 질문+벡터 맥락으로 그래프 시드 엔티티를 찾고 관계를 확장."""
    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    try:
        seed_text = f"{question}\n\n관련 문서 맥락:\n{vector_context}"
        entities = find_question_entities(driver, seed_text, fallback_question=question)
        relationships = retrieve_graph_context(driver, [e["id"] for e in entities])
        return entities, relationships
    finally:
        driver.close()


def generate_hybrid_answer(question, vector_context, graph_context):
    """③ Synthesis: 벡터 청크 + 그래프 관계를 함께 LLM에 넣어 답변(LCEL)."""
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY 또는 EMBEDDING_API_KEY를 설정해주세요.")

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "너는 SR 플랫폼 지식 질의응답 assistant다. "
                "아래 두 근거를 모두 사용해 한국어로 답변한다: "
                "(1) 벡터 검색으로 찾은 문서 chunk(사실·서술 근거), "
                "(2) 지식그래프에서 찾은 Entity 관계(개념 간 연결·인과). "
                "문서 chunk로 내용을 확인하고, 그래프 관계로 Entity 사이 연결을 설명한다. "
                "두 근거에 없는 내용은 '제공된 근거에서 확인할 수 없습니다.'라고 답한다. "
                "답변 마지막에 근거로 쓴 문서 section과 그래프 관계를 bullet로 표시한다.",
            ),
            (
                "human",
                "질문:\n{question}\n\n[문서 근거]\n{vector_context}\n\n[그래프 관계 근거]\n{graph_context}",
            ),
        ]
    )
    llm = ChatGoogleGenerativeAI(model=LLM_API_MODEL, google_api_key=LLM_API_KEY)
    chain = prompt | llm | StrOutputParser()

    return chain.invoke(
        {
            "question": question,
            "vector_context": vector_context or "(관련 문서 없음)",
            "graph_context": graph_context or "(관련 그래프 관계 없음)",
        }
    )


def hybrid_answer(question):
    """Vector→Graph 순차 하이브리드 전체 실행. (vector_docs, entities, relationships, answer) 반환.
    단계별 부분실패 격리: vector 실패 시 graph-only, graph 실패 시 vector-only로 저하 동작."""
    try:
        vector_docs = retrieve_vector(question)
    except Exception:
        vector_docs = []
    vector_context = format_documents(vector_docs)

    try:
        entities, relationships = retrieve_graph(question, vector_context)
    except Exception:
        entities, relationships = [], []
    graph_context = build_graph_context(entities, relationships)

    answer = generate_hybrid_answer(question, vector_context, graph_context)
    return vector_docs, entities, relationships, answer


def main():
    question = " ".join(sys.argv[1:]).strip()

    if not question:
        question = input("질문을 입력하세요: ").strip()

    if not question:
        raise RuntimeError("질문이 비어 있습니다.")

    vector_docs, entities, relationships, answer = hybrid_answer(question)

    print(f"질문: {question}\n")
    print(f"[Vector 검색 청크] {len(vector_docs)}개")
    for d in vector_docs:
        print("-", d.metadata.get("section", "(section 없음)"))
    print(f"\n[Graph 시드 엔티티] {[e['id'] for e in entities]}")
    print(f"[Graph 관계] {len(relationships)}개\n")
    print("답변:")
    print(answer)


if __name__ == "__main__":
    main()
