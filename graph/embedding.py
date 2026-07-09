import os
from pathlib import Path
from dotenv import load_dotenv
from google import genai

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY")
EMBEDDING_API_MODEL = os.getenv("EMBEDDING_API_MODEL", "gemini-embedding-001")


def create_embedding(text):
    if not EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY 또는 LLM_API_KEY를 설정해주세요.")
    client = genai.Client(api_key=EMBEDDING_API_KEY)
    response = client.models.embed_content(model=EMBEDDING_API_MODEL, contents=text)
    return response.embeddings[0].values
