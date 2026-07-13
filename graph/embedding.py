import os
import random
import re
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY") or os.getenv("LLM_API_KEY")
EMBEDDING_API_MODEL = os.getenv("EMBEDDING_API_MODEL", "gemini-embedding-001")

# 무료 티어 embed_content는 분당 100요청 제한 → 배치로 요청 수를 줄인다.
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "100"))
_RETRY_CAP_SEC = 60


def _client():
    if not EMBEDDING_API_KEY:
        raise RuntimeError("EMBEDDING_API_KEY 또는 LLM_API_KEY를 설정해주세요.")
    return genai.Client(api_key=EMBEDDING_API_KEY)


def _is_rate_limit(exc):
    # 상태 코드로만 판별(문자열 '429' 우연 포함 오판 방지)
    return getattr(exc, "code", None) == 429 or getattr(exc, "status", None) == "RESOURCE_EXHAUSTED"


def _retry_delay(exc, attempt):
    # 429 응답의 retryDelay를 우선 사용, 없으면 지수 백오프+지터(상한 60초)
    match = re.search(r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+)", str(exc))
    if match:
        return min(int(match.group(1)) + 1, _RETRY_CAP_SEC)
    return min(_RETRY_CAP_SEC, 2 ** attempt * 5 + random.uniform(0, 2))


def create_embedding(text):
    """단일 텍스트 임베딩(질의 측 등)."""
    response = _client().models.embed_content(model=EMBEDDING_API_MODEL, contents=text)
    return response.embeddings[0].values


def create_embeddings(texts, batch_size=EMBED_BATCH_SIZE, max_retries=3):
    """여러 텍스트를 배치로 임베딩. 요청 수를 (텍스트 수 → 배치 수)로 줄여 분당
    rate limit을 피하고, 429면 retryDelay(없으면 백오프)만큼 대기 후 재시도한다.
    반환 순서는 입력 순서와 동일하며, 개수 불일치는 즉시 예외로 드러낸다(조용한 오정렬 방지)."""
    if not texts:
        return []
    max_retries = max(1, max_retries)
    client = _client()
    vectors = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start:start + batch_size]
        for attempt in range(max_retries):
            try:
                response = client.models.embed_content(model=EMBEDDING_API_MODEL, contents=chunk)
                if len(response.embeddings) != len(chunk):
                    raise RuntimeError(
                        f"임베딩 개수 불일치: 요청 {len(chunk)} != 응답 {len(response.embeddings)}"
                    )
                vectors.extend(e.values for e in response.embeddings)
                break
            except errors.APIError as exc:
                if _is_rate_limit(exc) and attempt < max_retries - 1:
                    time.sleep(_retry_delay(exc, attempt))
                    continue
                raise
    if len(vectors) != len(texts):
        raise RuntimeError(f"임베딩 총 개수 불일치: 입력 {len(texts)} != 결과 {len(vectors)}")
    return vectors
