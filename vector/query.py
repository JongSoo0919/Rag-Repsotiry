import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore

from vector.ingest import normalize_gemini_embedding_model


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("GOOGLE_API_KEY")
EMBEDDING_API_MODEL = os.getenv("EMBEDDING_API_MODEL", "gemini-embedding-001")
LLM_API_KEY = os.getenv("LLM_API_KEY") or EMBEDDING_API_KEY
LLM_API_MODEL = os.getenv("LLM_API_MODEL", "gemini-2.5-flash")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "rag_poc_chunks")
TOP_K = int(os.getenv("RAG_TOP_K", "3"))


def create_embeddings():
    if not EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY를 설정해주세요.")

    return GoogleGenerativeAIEmbeddings(
        model=normalize_gemini_embedding_model(EMBEDDING_API_MODEL),
        google_api_key=EMBEDDING_API_KEY,
    )


def create_retriever():
    embeddings = create_embeddings()
    vector_store = QdrantVectorStore.from_existing_collection(
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        url=QDRANT_URL,
    )
    return vector_store.as_retriever(search_kwargs={"k": TOP_K})


def format_documents(documents):
    context_parts = []

    for index, document in enumerate(documents, start=1):
        section = document.metadata.get("section", "(section 없음)")
        context_parts.append(
            f"[문서 {index}]\n"
            f"section: {section}\n"
            f"text:\n{document.page_content}"
        )

    return "\n\n---\n\n".join(context_parts)


def print_documents(question, documents):
    print(f"질문: {question}")
    print(f"collection: {COLLECTION_NAME}")
    print(f"검색 결과: {len(documents)}개")
    print()

    for index, document in enumerate(documents, start=1):
        section = document.metadata.get("section", "(section 없음)")

        print("=" * 80)
        print(f"result {index}")
        print(f"section: {section}")
        print("=" * 80)
        print(document.page_content[:1200])
        print()


def generate_answer(question, documents):
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY 또는 EMBEDDING_API_KEY를 설정해주세요.")

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "너는 SR 플랫폼 문서 기반 질의응답 assistant다. "
                "제공된 context에 있는 내용만 근거로 한국어로 답변한다. "
                "context에 없는 내용은 '제공된 문서에서 확인할 수 없습니다.'라고 답변한다. "
                "답변 마지막에 참고한 section을 bullet로 표시한다.",
            ),
            (
                "human",
                "질문:\n{question}\n\ncontext:\n{context}",
            ),
        ]
    )
    llm = ChatGoogleGenerativeAI(
        model=LLM_API_MODEL,
        google_api_key=LLM_API_KEY,
        temperature=0,
    )
    chain = prompt | llm | StrOutputParser()

    return chain.invoke(
        {
            "question": question,
            "context": format_documents(documents),
        }
    )


def main():
    args = [arg for arg in sys.argv[1:] if arg != "--debug"]
    debug = "--debug" in sys.argv[1:]
    question = " ".join(args).strip()

    if not question:
        question = input("질문을 입력하세요: ").strip()

    if not question:
        raise RuntimeError("질문이 비어 있습니다.")

    retriever = create_retriever()
    documents = retriever.invoke(question)

    if debug:
        print_documents(question, documents)

    answer = generate_answer(question, documents)

    print(f"질문: {question}")
    print()
    print("답변:")
    print(answer)


if __name__ == "__main__":
    main()
