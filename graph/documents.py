import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from preprocessing.masking import mask_text


PROJECT_ROOT = Path(__file__).resolve().parents[1]

load_dotenv(PROJECT_ROOT / ".env")
load_dotenv(PROJECT_ROOT / ".idea" / ".env")

LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("EMBEDDING_API_KEY")
LLM_API_MODEL = os.getenv("LLM_API_MODEL", "gemini-2.5-flash")

DOCUMENTS_DIR = PROJECT_ROOT / "data"
# 그래프 추출 대상 폴더 (명시 지정, 비재귀). 여기 있는 .md만 읽는다.
#   - data/public/  : 커밋되는 공개 샘플
#   - data/private/ : gitignore되는 비공개 원문(Loki sample.md 등)
DOCUMENT_SOURCE_DIRS = [DOCUMENTS_DIR / "public", DOCUMENTS_DIR / "private"]


# 1. 원본 문서 조각 준비
# DOCUMENT_SOURCE_DIRS에 명시된 폴더 각각에서 비재귀로 .md 파일을 읽어
# {문서 ID: 본문} 형태로 반환한다.
# 문서 ID는 data/ 기준 상대경로(확장자 제외)를 사용해 하위 폴더 간 이름 충돌을 피한다.
# 예: data/public/k8s-sample.md -> "public/k8s-sample", data/private/sample.md -> "private/sample"
def load_documents():
    documents = {}

    for source_dir in DOCUMENT_SOURCE_DIRS:
        if not source_dir.is_dir():
            continue

        for path in sorted(source_dir.rglob("*.md")):
            if path.is_symlink() or any(part.startswith("_") for part in path.relative_to(source_dir).parts):
                continue  # 재귀 + 링크 차단 + _ 접두 파일/폴더(메타) 제외

            content = mask_text(path.read_text(encoding="utf-8")).strip()  # 적재 전 마스킹

            if content:
                doc_id = path.relative_to(DOCUMENTS_DIR).with_suffix("").as_posix()
                documents[doc_id] = content

    if not documents:
        raise RuntimeError(
            f"{DOCUMENT_SOURCE_DIRS} 에서 읽을 .md 문서를 찾지 못했습니다. "
            f"data/public/ 또는 data/private/ 에 문서를 넣으세요."
        )

    return documents


def build_extraction_prompt(documents):
    document_text = "\n\n".join(
        f"[문서 ID: {document_id}]\n{content.strip()}"
        for document_id, content in documents.items()
    )

    return f"""
너는 문서를 읽고 Knowledge Graph의 Node와 Edge를 추출하는 assistant다.

규칙:
- 반드시 JSON만 출력한다.
- markdown code fence를 쓰지 않는다.
- nodes는 문서에서 중요한 개념, 기술, 리소스, 시스템, 원인, 조치, 담당자만 뽑는다.
- node id는 문서에 나온 고유명사 표기를 그대로 사용한다.
- 예를 들어 문서에 Service-JS라고 나오면 반드시 Service-JS라고 써야 하며 Service로 바꾸면 안 된다.
- 문서에 없는 외부 지식은 nodes와 edges에 추가하지 않는다.
- edges는 두 node 사이의 의미 있는 관계만 뽑는다.
- edge의 source와 target은 반드시 nodes에 존재하는 id를 사용한다.
- relation은 영문 snake_case로 작성한다. (예: causes, resolved_by, requires, exposes, manages)
- confidence는 0.0부터 1.0 사이 숫자로 작성한다.
- source_document는 반드시 입력 문서 ID 중 하나를 사용한다.

JSON 형식:
{{
  "nodes": [
    {{
      "id": "Loki Dashboard",
      "type": "system",
      "description": "로그를 시각화하는 대시보드",
      "source_document": "sample"
    }}
  ],
  "edges": [
    {{
      "source": "Loki Dashboard Issue",
      "target": "Missing Label",
      "relation": "caused_by",
      "description": "시각화 패널이 0으로 나오는 문제는 Label 누락 때문이다",
      "confidence": 0.9,
      "source_document": "sample"
    }}
  ]
}}

문서:
{document_text}
""".strip()


def extract_json(text):
    """LLM 응답에서 JSON 객체만 꺼낸다."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```json\s*", "", cleaned)
    cleaned = re.sub(r"^```\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)

    start = cleaned.find("{")
    end = cleaned.rfind("}")

    if start == -1 or end == -1:
        raise RuntimeError(f"LLM 응답에서 JSON을 찾지 못했습니다.\n응답:\n{text}")

    return json.loads(cleaned[start : end + 1])


def extract_graph_data_with_llm(documents=None):
    """문서를 LLM에 읽혀 nodes/edges를 추출한다."""
    if not LLM_API_KEY:
        raise RuntimeError(
            "LLM_API_KEY 또는 EMBEDDING_API_KEY를 설정해주세요. "
            "Graph RAG는 문서에서 Entity/관계를 추출하기 위해 LLM이 필요합니다."
        )

    if documents is None:
        documents = load_documents()

    client = genai.Client(api_key=LLM_API_KEY)
    response = client.models.generate_content(
        model=LLM_API_MODEL,
        contents=build_extraction_prompt(documents),
        config=types.GenerateContentConfig(temperature=0),
    )

    if not response.text:
        raise RuntimeError("LLM이 빈 응답을 반환했습니다 (finish_reason 확인 필요).")

    return extract_json(response.text)
