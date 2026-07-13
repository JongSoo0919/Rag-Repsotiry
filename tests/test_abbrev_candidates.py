from preprocessing.abbrev_candidates import (
    detect_candidates,
    find_caps_tokens,
    find_defined_abbreviations,
)


def test_find_defined_abbreviation():
    text = "서비스 요청(SR) 처리"
    assert ("SR", "서비스 요청") in find_defined_abbreviations(text)


def test_find_caps_tokens_excludes_stopwords():
    tokens = find_caps_tokens("WAS 재기동. TODO 확인. CM 반영.")
    assert "WAS" in tokens
    assert "CM" in tokens
    assert "TODO" not in tokens  # 스톱워드 제외


def test_detect_counts_and_excludes_known():
    docs = {"d1": "SR 접수. SR 처리.", "d2": "WAS 재기동."}
    cands = detect_candidates(docs, known={"SR"})
    assert "SR" not in cands  # 이미 사전에 있으면 제외
    assert cands["WAS"]["count"] == 1
    assert "d2" in cands["WAS"]["seen_in"]


def test_defined_pattern_feeds_hint():
    cands = detect_candidates({"d1": "서비스 요청(SR) 안내"}, known=set())
    assert cands["SR"]["hint"] == "서비스 요청"


def test_caps_tokens_with_korean_particle():
    tokens = find_caps_tokens("SR을 접수하고 CM에서 반영. K8S를 설정.")
    assert "SR" in tokens
    assert "CM" in tokens
    assert "K8S" in tokens


def test_caps_tokens_not_inside_word():
    # 약어가 영숫자 단어 안에 있으면 잡지 않는다
    assert "SR" not in find_caps_tokens("USRID 확인")
