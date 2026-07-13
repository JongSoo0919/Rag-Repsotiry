"""골든셋 채점 — 순수 함수(무API·결정론).

기록된 트랙 출력만으로 지표를 낸다. 그래서 실제 트랙 호출(쿼터)과 분리되고
단위테스트가 쿼터 없이 돈다. 지표:
  - source_recall  : 기대 출처가 검색결과에 있나 (모든 트랙)
  - entity_recall  : 기대 엔티티가 매칭됐나 (graph/hybrid만)
  - keyword_coverage: 답변에 핵심어가 있나 (어휘 존재만; 근거성 프록시 아님)
  - negative_correct: 정답 없는 질문에 환각 안 하고 거부/무근거였나
"""

THRESH_SOURCE = 0.5
THRESH_ENTITY = 0.5
THRESH_KEYWORD = 0.5

REFUSAL_MARKERS = [
    "확인할 수 없",
    "찾지 못",
    "확인되지 않",
    "근거가 없",
    "관련된 entity를 찾지 못",
    "제공된 문서에서 확인할 수 없",
    "제공된 근거에서 확인할 수 없",
    "그래프에서 확인할 수 없",
]


def _norm(value):
    return (value or "").strip().lower()


def _recall(expected, got):
    exp = [_norm(x) for x in (expected or []) if _norm(x)]
    if not exp:
        return None  # 기대가 없으면 채점 대상 아님
    have = {_norm(x) for x in (got or []) if _norm(x)}
    return sum(1 for e in exp if e in have) / len(exp)


def source_recall(expected, retrieved):
    return _recall(expected, retrieved)


def entity_recall(expected, matched):
    return _recall(expected, matched)


def keyword_coverage(keywords, answer):
    kws = [k for k in (keywords or []) if str(k).strip()]
    if not kws:
        return None
    text = _norm(answer)
    return sum(1 for k in kws if _norm(k) in text) / len(kws)


def is_refusal(answer):
    text = _norm(answer)
    return any(_norm(m) in text for m in REFUSAL_MARKERS)


# 정답이 없어야 할 질문에서 '단정(how-to)'을 나타내는 표지(휴리스틱).
# 거부하면서 동시에 이런 단정을 하면 부분 환각으로 의심한다.
POSITIVE_CLAIM_MARKERS = [
    "하세요", "하면 됩니다", "설정법은", "방법은", "사용합니다", "씁니다",
    "설정합니다", "권장합니다", "다음과 같습니다",
]


def has_positive_claim(answer):
    text = _norm(answer)
    return any(_norm(m) in text for m in POSITIVE_CLAIM_MARKERS)


def negative_correct(retrieved_sources, answer):
    """정답이 없어야 하는 질문: 환각 없이 거부/무근거였나.

    - 거부 문구가 있어도 함께 단정하면 부분 환각 의심 -> None(사람 판정 보류).
    - 검색이 비어도 답변이 단정(환각)이면 실패. 거부/무답이면 통과.
    - 검색 근거가 있으면 답변이 거부를 명시해야 통과.
    """
    refused = is_refusal(answer)
    if refused and has_positive_claim(answer):
        return None  # 부분 환각 의심 -> 자동 판정 보류
    if not retrieved_sources:
        return refused or not _norm(answer)
    return refused


def score_case(case, output, retrieval_only=False):
    """case(골든셋 항목) + output(트랙 정규화 출력) -> 지표/통과 dict."""
    track = output.get("track")
    result = {"id": case.get("id"), "track": track}

    if case.get("expect_refusal"):
        if retrieval_only:
            # answer가 없어 거부 판정 불가 -> 검색 공백만으로 판정.
            # 근거가 있으면(비공백) 미채점(None): 강제 실패시키지 않는다.
            ok = True if not output.get("retrieved_sources") else None
        else:
            ok = negative_correct(output.get("retrieved_sources"), output.get("answer"))
        result.update({"negative": True, "negative_correct": ok, "passed": ok})
        return result

    src = source_recall(case.get("expect_sources"), output.get("retrieved_sources"))
    ent = (
        entity_recall(case.get("expect_entities"), output.get("matched_entities"))
        if track in ("graph", "hybrid")
        else None  # vector는 엔티티를 만들지 않으므로 미채점
    )
    kw = None if retrieval_only else keyword_coverage(
        case.get("expect_answer_contains"), output.get("answer")
    )

    checks = []
    if src is not None:
        checks.append(src >= THRESH_SOURCE)
    if ent is not None:
        checks.append(ent >= THRESH_ENTITY)
    if kw is not None:
        checks.append(kw >= THRESH_KEYWORD)

    result.update({
        "negative": False,
        "source_recall": src,
        "entity_recall": ent,
        "keyword_coverage": kw,
        "passed": all(checks) if checks else None,
    })
    return result
