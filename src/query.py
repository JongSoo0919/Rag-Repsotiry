import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from qdrant_client import QdrantClient

from ingest import create_embedding


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "rag_poc_chunks")
TOP_K = int(os.getenv("RAG_TOP_K", "3"))
LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
LLM_API_MODEL = os.getenv("LLM_API_MODEL", "gemini-2.5-flash")


def search_chunks(question, top_k=TOP_K):
    qdrant = QdrantClient(url=QDRANT_URL)
    question_vector = create_embedding(question)

    response = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        query=question_vector,
        limit=top_k * 3,
        with_payload=True,
        with_vectors=False,
    )
    return deduplicate_results(response.points, top_k)


def deduplicate_results(points, limit):
    results = []
    seen = set()

    for point in points:
        payload = point.payload or {}
        key = (payload.get("section"), payload.get("text"))

        if key in seen:
            continue

        seen.add(key)
        results.append(point)

        if len(results) == limit:
            break

    return results


def print_results(question, results):
    print(f"질문: {question}")
    print(f"collection: {COLLECTION_NAME}")
    print(f"검색 결과: {len(results)}개")
    print()

    for index, result in enumerate(results, start=1):
        payload = result.payload or {}
        section = payload.get("section", "(section 없음)")
        text = payload.get("text", "")
        score = result.score

        print("=" * 80)
        print(f"result {index}")
        print(f"score: {score:.4f}")
        print(f"section: {section}")
        print("=" * 80)
        print(text[:1200])
        print()


def build_context(results):
    context_parts = []

    for index, result in enumerate(results, start=1):
        payload = result.payload or {}
        section = payload.get("section", "(section 없음)")
        text = payload.get("text", "")

        context_parts.append(
            f"[문서 {index}]\n"
            f"section: {section}\n"
            f"text:\n{text}"
        )

    return "\n\n---\n\n".join(context_parts)


def generate_answer(question, results):
    if not LLM_API_KEY:
        raise RuntimeError("LLM_API_KEY 또는 EMBEDDING_API_KEY를 설정해주세요.")

    context = build_context(results)
    client = genai.Client(api_key=LLM_API_KEY)

    prompt = f"""
너는 SR 플랫폼 문서 기반 질의응답 assistant다.

규칙:
- 아래 context에 있는 내용만 근거로 답변한다.
- context에 없는 내용은 "제공된 문서에서 확인할 수 없습니다."라고 답변한다.
- 답변은 한국어로 작성한다.
- 사용자의 질문에 직접 답한다.
- 답변 마지막에 참고한 section을 bullet로 표시한다.

질문:
{question}

context:
{context}
""".strip()

    response = client.models.generate_content(
        model=LLM_API_MODEL,
        contents=prompt,
    )

    return response.text


def main():
    args = [arg for arg in sys.argv[1:] if arg != "--debug"]
    debug = "--debug" in sys.argv[1:]
    question = " ".join(args).strip()

    if not question:
        question = input("질문을 입력하세요: ").strip()

    if not question:
        raise RuntimeError("질문이 비어 있습니다.")

    results = search_chunks(question)

    if debug:
        print_results(question, results)

    answer = generate_answer(question, results)

    print(f"질문: {question}")
    print()
    print("답변:")
    print(answer)


if __name__ == "__main__":
    main()
