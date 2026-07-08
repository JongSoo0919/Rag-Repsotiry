# RAG Repository

Confluence 문서를 가져와 Qdrant에 저장하고, 질문하면 관련 chunk를 검색해 LLM으로 답변하는 Python RAG PoC입니다.

## 구성

```text
Confluence
→ fetch_confluence_sample.py
→ data/sample.md
→ chucker.py
→ ingest.py
→ Qdrant
→ query.py
→ web_app.py
```

## 준비

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
```

`.env`에 본인 API Key와 Confluence 정보를 입력합니다.

## Qdrant 실행

```bash
docker compose up -d
```

Dashboard:

```text
http://localhost:6333/dashboard
```

## 데이터 수집 및 저장

```bash
.venv/bin/python src/fetch_confluence_sample.py
.venv/bin/python src/chucker.py
.venv/bin/python src/ingest.py
```

## CLI 질문

```bash
.venv/bin/python src/query.py '질문을 입력하세요'
```

검색된 근거까지 보려면:

```bash
.venv/bin/python src/query.py --debug '질문을 입력하세요'
```

## 웹 실행

```bash
.venv/bin/uvicorn web_app:app --app-dir src --host 0.0.0.0 --port 8001
```

접속:

```text
http://localhost:8001
```

## 보안

아래 파일과 디렉터리는 커밋하지 않습니다.

```text
.env
.idea/
qdrant_storage/
data/sample.md
```

실제 키와 계정 정보는 `.env.example`이 아니라 로컬 `.env`에만 저장합니다.
