import os
import hashlib
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from vector.chucker import split_by_sections

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_PATH = PROJECT_ROOT / "data" / "sample.md"

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("OPENAI_API_KEY")
EMBEDDING_API_MODEL = os.getenv("EMBEDDING_API_MODEL", "gemini-embedding-001")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "rag_poc_chunks")

VECTOR_SIZE = int(os.getenv("EMBEDDING_VECTOR_SIZE", "0"))


def create_embedding(text):
    if not EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY를 설정해주세요.")

    if EMBEDDING_API_MODEL.startswith("gemini"):
        client = genai.Client(api_key=EMBEDDING_API_KEY)
        response = client.models.embed_content(
            model=EMBEDDING_API_MODEL,
            contents=text,
        )
        return response.embeddings[0].values

    if EMBEDDING_API_MODEL.startswith("text-embedding"):
        client = OpenAI(api_key=EMBEDDING_API_KEY)
        response = client.embeddings.create(
            model=EMBEDDING_API_MODEL,
            input=text,
        )
        return response.data[0].embedding

    raise ValueError(f"지원하지 않는 embedding model입니다: {EMBEDDING_API_MODEL}")


def get_embedding_size():
    embedding = create_embedding("vector size check")
    return len(embedding)


def create_collection(qdrant, vector_size):
    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=vector_size,
            distance=Distance.COSINE,
        ),
    )


def ensure_collection(qdrant, vector_size):
    collections = qdrant.get_collections().collections
    collection_names = [collection.name for collection in collections]

    if COLLECTION_NAME not in collection_names:
        create_collection(qdrant, vector_size)
        return

    info = qdrant.get_collection(COLLECTION_NAME)
    current_size = info.config.params.vectors.size

    if current_size != vector_size:
        raise RuntimeError(
            f"Qdrant collection vector size가 다릅니다. "
            f"collection={current_size}, current_model={vector_size}. "
            f"QDRANT_COLLECTION 이름을 바꾸거나 기존 collection을 삭제하세요."
        )


def main():
    qdrant = QdrantClient(url=QDRANT_URL)
    vector_size = VECTOR_SIZE if VECTOR_SIZE > 0 else get_embedding_size()

    ensure_collection(qdrant, vector_size)

    text = SAMPLE_PATH.read_text(encoding="utf-8")
    chunks = split_by_sections(text)

    points = []

    for index, chunk in enumerate(chunks):
        if chunk["section"] == "metadata":
            continue

        embedding = create_embedding(chunk["text"])

        point_id = hashlib.md5(
            f"{SAMPLE_PATH}:{chunk['section']}:{chunk['text']}".encode("utf-8")
        ).hexdigest()

        point = PointStruct(
            id=point_id,
            vector=embedding,
            payload={
                "section": chunk["section"],
                "text": chunk["text"],
                "source_file": str(SAMPLE_PATH),
                "chunk_index": index,
            },
        )

        points.append(point)

    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=points,
    )

    print(f"저장 완료: {len(points)} chunks")
    print(f"collection: {COLLECTION_NAME}")
    print(f"embedding model: {EMBEDDING_API_MODEL}")
    print(f"vector size: {vector_size}")


if __name__ == "__main__":
    main()
