# RAG Repository

Confluence 문서를 기반으로 한 Python RAG PoC입니다. 두 가지 검색 방식을 함께 다룹니다.

- **Vector RAG** (`vector/`): 문서를 chunk로 나눠 Qdrant에 임베딩 저장하고, 질문과 유사한 chunk를 검색해 LLM으로 답변합니다.
- **Graph RAG** (`graph/`): 문서에서 Entity와 관계를 추출해 Neo4j에 저장하고, 그래프 탐색으로 근거를 모아 답변합니다.

## 구성

```text
Vector RAG (Qdrant)
  Confluence → vector/fetch_confluence_sample.py → data/sample.md
             → vector/ingest.py → Qdrant → vector/query.py / vector/web_app.py

Graph RAG (Neo4j)
  문서 → graph/documents.py(LLM Entity/관계 추출)
       → graph/ingest.py → Neo4j → graph/query.py / graph/web_app.py
```

> 모든 모듈은 패키지 절대 import(`from vector.x`, `from graph.x`)를 사용합니다.
> 반드시 **프로젝트 루트에서 `python -m` 형태**로 실행하세요. (`python vector/query.py` 방식은 import가 깨집니다.)

## 준비

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

`.env`에 본인 API Key와 Confluence 정보, Neo4j 접속 정보를 입력합니다.

## 인프라 실행 (Qdrant + Neo4j)

```bash
docker compose up -d
```

| 서비스 | 주소 |
| --- | --- |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| Neo4j Browser | http://localhost:7474 (기본 계정 neo4j / password) |

## Vector RAG

### 데이터 수집 및 저장

```bash
.venv/bin/python -m vector.fetch_confluence_sample   # Confluence → data/sample.md
.venv/bin/python -m vector.chucker                   # (선택) chunk 분할 미리보기
.venv/bin/python -m vector.ingest                    # chunk 임베딩 → Qdrant
```

### CLI 질문

```bash
.venv/bin/python -m vector.query '질문을 입력하세요'
.venv/bin/python -m vector.query --debug '질문을 입력하세요'   # 검색된 근거까지 표시
```

### LangChain 버전 (별도 collection)

```bash
.venv/bin/python -m vector.langchain_ingest
.venv/bin/python -m vector.langchain_query '질문을 입력하세요'
```

### 웹 실행

```bash
.venv/bin/uvicorn vector.web_app:app --host 0.0.0.0 --port 8001
```

접속: http://localhost:8001

## Graph RAG

### 그래프 적재

```bash
.venv/bin/python -m graph.ingest   # 문서에서 Entity/관계 추출 → Neo4j
```

> `LLM_API_KEY`가 없거나 호출 한도를 초과하면 로컬 fallback 데이터로 동작합니다.

### CLI 질문

```bash
.venv/bin/python -m graph.query 'Deployment를 외부 통신하려면 어떻게 해야해?'
```

### 웹 실행

```bash
.venv/bin/uvicorn graph.web_app:app --host 0.0.0.0 --port 8002
```

접속: http://localhost:8002

## 보안

아래 파일과 디렉터리는 커밋하지 않습니다.

```text
.env, .env.*        # 실제 키·계정 (.env.example만 커밋)
.idea/
qdrant_storage/     # Qdrant 로컬 데이터
neo4j_data/, neo4j_logs/
data/*              # sample.md 등 수집 원문 (.gitkeep만 유지)
private_reports/    # 내부 페이지 제목·URL 등 비공개 산출물
```

실제 키와 계정 정보는 `.env.example`이 아니라 로컬 `.env`에만 저장합니다.
