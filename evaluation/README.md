# 평가 하네스 (evaluation)

RAG 3트랙(vector/graph/hybrid)의 검색·근거 품질을 **고정 골든셋**으로 측정한다.
목적은 "좋은가?"의 절대평가가 아니라, 데이터를 늘리거나 코드를 고쳤을 때
**"안 깨졌나 / 수치가 어떻게 변했나"**를 보는 회귀 눈금자다.

## 구성
- `golden_set.yaml` — 질문 + 기대 결과(출처·엔티티·핵심어·거부여부). **id/question은 회귀 비교선이라 변경 금지**, 추가만.
- `scoring.py` — 채점(순수 함수, 무API·결정론). `source_recall`·`entity_recall`·`keyword_coverage`·`negative_correct`.
- `run_eval.py` — 골든셋을 트랙에 통과시켜 채점·리포트.
- `reports/` — 실행 결과(JSON, git 미추적).

## 원칙: 데이터셋·채점은 무쿼터, 점수 산출만 API
채점 로직은 트랙 출력만 받는 순수 함수라 `tests/test_eval_scoring.py`로 쿼터 없이 검증된다.
실제 점수는 트랙 호출(Neo4j/Qdrant + Gemini)이 필요하다.

## 사용
```bash
# 골든셋 구조 검증 (무API)
.venv/bin/python -m evaluation.run_eval --dry-run

# 검색 지표만 (생성 생략 → generate_content 쿼터 절약)
.venv/bin/python -m evaluation.run_eval --retrieval-only

# 트랙/케이스 한정
.venv/bin/python -m evaluation.run_eval --track vector
.venv/bin/python -m evaluation.run_eval --ids loki-viz-cause,deploy-external
```
> graph/hybrid는 `generate_content`(하루 20회)를 쓰므로, 먼저 `--retrieval-only`로
> 검색 지표를 보고 쿼터가 있을 때만 전체(생성 포함)를 돌리는 걸 권장.

## 지표
| 지표 | 대상 | 의미 |
| --- | --- | --- |
| source_recall | 전 트랙 | 기대 출처 문서가 검색됐나 |
| entity_recall | graph·hybrid | 기대 엔티티가 매칭됐나 |
| keyword_coverage | 전 트랙(생성 시) | 답변에 핵심어가 있나(어휘 존재만; 근거성 아님) |
| negative_correct | 부정 케이스 | 문서에 없는 질문에 환각 없이 거부/무근거였나 |
