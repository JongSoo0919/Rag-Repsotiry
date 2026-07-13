from evaluation import scoring


def test_source_recall():
    assert scoring.source_recall(["private/sample"], ["private/sample", "x"]) == 1.0
    assert scoring.source_recall(["a", "b"], ["a"]) == 0.5
    assert scoring.source_recall([], ["a"]) is None  # 기대 없으면 미채점


def test_entity_recall_case_insensitive():
    assert scoring.entity_recall(["Loki Dashboard"], ["loki dashboard"]) == 1.0
    assert scoring.entity_recall(["Pod", "Service-JS"], ["Pod"]) == 0.5


def test_keyword_coverage():
    assert scoring.keyword_coverage(["Label"], "원인은 Label 누락입니다") == 1.0
    assert scoring.keyword_coverage(["Label", "권한"], "label 문제") == 0.5
    assert scoring.keyword_coverage([], "x") is None


def test_is_refusal():
    assert scoring.is_refusal("제공된 문서에서 확인할 수 없습니다.")
    assert not scoring.is_refusal("설정법은 다음과 같습니다")


def test_negative_correct():
    assert scoring.negative_correct([], "확인할 수 없습니다") is True          # 거부
    assert scoring.negative_correct([], None) is True                         # 무답
    assert scoring.negative_correct([], "블록체인은 PoW를 사용합니다") is False  # 공백+단정 환각
    assert scoring.negative_correct(["x"], "그래프에서 확인할 수 없습니다") is True  # 거부
    assert scoring.negative_correct(["x"], "설정법은 A") is False              # 근거+단정


def test_negative_partial_hallucination_is_none():
    # 거부 문구 + 단정 동시 -> 부분 환각 의심 -> None(보류)
    assert scoring.negative_correct(["x"], "확인할 수 없으나 일반적으로 사용합니다") is None


def test_score_case_positive_graph():
    case = {"id": "g", "expect_sources": ["public/k8s-sample"],
            "expect_entities": ["Deployment"], "expect_answer_contains": ["Service"]}
    out = {"track": "graph", "retrieved_sources": ["public/k8s-sample"],
           "matched_entities": ["Deployment"], "answer": "Service-JS로 연결한다"}
    assert scoring.score_case(case, out)["passed"] is True


def test_score_case_vector_not_penalized_for_entities():
    case = {"id": "v", "expect_sources": ["private/sample"],
            "expect_entities": ["Loki Dashboard"], "expect_answer_contains": ["Label"]}
    out = {"track": "vector", "retrieved_sources": ["private/sample"],
           "matched_entities": [], "answer": "Label 누락이 원인"}
    res = scoring.score_case(case, out)
    assert res["entity_recall"] is None  # vector는 엔티티 미채점
    assert res["passed"] is True


def test_score_case_retrieval_only_skips_keyword():
    case = {"id": "g", "expect_sources": ["public/k8s-sample"],
            "expect_entities": ["Deployment"], "expect_answer_contains": ["Service"]}
    out = {"track": "graph", "retrieved_sources": ["public/k8s-sample"],
           "matched_entities": ["Deployment"], "answer": None}
    res = scoring.score_case(case, out, retrieval_only=True)
    assert res["keyword_coverage"] is None
    assert res["passed"] is True


def test_score_case_negative_full_generation():
    case = {"id": "n", "expect_refusal": True}
    refuse = {"track": "vector", "retrieved_sources": ["x"], "matched_entities": [], "answer": "제공된 문서에서 확인할 수 없습니다"}
    assert scoring.score_case(case, refuse)["passed"] is True
    halluc = {"track": "vector", "retrieved_sources": ["x"], "matched_entities": [], "answer": "설정법은 A"}
    assert scoring.score_case(case, halluc)["passed"] is False


def test_score_case_negative_retrieval_only():
    case = {"id": "n", "expect_refusal": True}
    empty = {"track": "graph", "retrieved_sources": [], "matched_entities": [], "answer": None}
    assert scoring.score_case(case, empty, retrieval_only=True)["passed"] is True  # 검색 공백 -> 통과
    withsrc = {"track": "vector", "retrieved_sources": ["x"], "matched_entities": [], "answer": None}
    assert scoring.score_case(case, withsrc, retrieval_only=True)["passed"] is None  # 근거 있고 answer 없음 -> 미채점
