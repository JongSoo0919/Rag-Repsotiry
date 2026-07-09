import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

from vector.chucker import load_documents, split_by_sections


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("GOOGLE_API_KEY")
EMBEDDING_API_MODEL = os.getenv("EMBEDDING_API_MODEL", "gemini-embedding-001")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "rag_poc_chunks")


def normalize_gemini_embedding_model(model_name: str) -> str:
    if model_name.startswith("models/"):
        return model_name
    return f"models/{model_name}"


def create_embeddings():
    if not EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY를 설정해주세요.")

    return GoogleGenerativeAIEmbeddings(
        model=normalize_gemini_embedding_model(EMBEDDING_API_MODEL),
        google_api_key=EMBEDDING_API_KEY,
    )


def build_documents():
    documents = []
    ids = []
    for doc_id, text in load_documents():
        chunks = split_by_sections(text)
        for index, chunk in enumerate(chunks):
            if chunk["section"] == "metadata":
                continue
            metadata = {
                "section": chunk["section"],
                "source_file": doc_id,
                "chunk_index": index,
            }
            documents.append(Document(page_content=chunk["text"], metadata=metadata))
            ids.append(hashlib.md5(
                f"{doc_id}:{chunk['section']}:{chunk['text']}".encode("utf-8")
            ).hexdigest())
    return documents, ids


def ensure_collection(qdrant, vector_size):
    if not qdrant.collection_exists(COLLECTION_NAME):
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=vector_size,
                distance=Distance.COSINE,
            ),
        )
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
    embeddings = create_embeddings()
    vector_size = len(embeddings.embed_query("vector size check"))
    qdrant = QdrantClient(url=QDRANT_URL)

    ensure_collection(qdrant, vector_size)

    vector_store = QdrantVectorStore(
        client=qdrant,
        collection_name=COLLECTION_NAME,
        embedding=embeddings,
    )

    documents, ids = build_documents()
    vector_store.add_documents(documents=documents, ids=ids)

    print(f"LangChain 저장 완료: {len(documents)} chunks")
    print(f"collection: {COLLECTION_NAME}")
    print(f"embedding model: {EMBEDDING_API_MODEL}")
    print(f"vector size: {vector_size}")


if __name__ == "__main__":
    main()
