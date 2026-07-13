"""약어 후보 탐지기 (반자동 사전 구축의 1단계).

data/public, data/private 의 .md 문서를 스캔해 '약어 후보'를 모은다.
  - "정식명칭(약어)" 패턴: 문서가 스스로 정의해준 약어 (예: "서비스 요청(SR)")
  - 반복되는 대문자 약어 토큰 (예: SR, CM, WAS)

결과는 data/private/aliases.candidates.yaml 로 저장된다(git 미추적).
사람이 검토해 canonical(정식명칭)을 채운 뒤 data/private/aliases.yaml 로 옮긴다.

탐지 로직(find_*, detect_candidates)은 순수 함수라 쿼터 없이 테스트된다.
"""
import re

import yaml

from preprocessing.aliases import PROJECT_ROOT, build_alias_map

DATA_DIR = PROJECT_ROOT / "data"
SOURCE_DIRS = [DATA_DIR / "public", DATA_DIR / "private"]
CANDIDATES_PATH = DATA_DIR / "private" / "aliases.candidates.yaml"

# "정식명칭(약어)" 패턴: 괄호 앞의 이름(group1) + 괄호 안 영문 약어(group2)
DEFINED_PATTERN = re.compile(
    r"([가-힣A-Za-z0-9][가-힣A-Za-z0-9 ·/\-]{1,39})\(\s*([A-Za-z][A-Za-z0-9\-]{1,9})\s*\)"
)
# 반복 가능성이 있는 대문자 약어(2~6자). ASCII 경계 기준이라 한글 조사(SR을, CM에서)가 붙어도 잡는다.
CAPS_PATTERN = re.compile(r"(?<![A-Za-z0-9])[A-Z][A-Z0-9]{1,5}(?![A-Za-z0-9])")

# 약어로 보기 어려운 흔한 토큰(노이즈 감소용, 최소만)
STOPWORDS = {"OK", "TODO", "FIXME", "NOTE", "YES", "NO", "AND", "OR", "THE", "ID", "URL"}


def find_defined_abbreviations(text):
    """'정식명칭(약어)' 패턴에서 (약어, 힌트=정식명칭 후보) 목록을 뽑는다."""
    return [(surface.strip(), hint.strip()) for hint, surface in DEFINED_PATTERN.findall(text)]


def find_caps_tokens(text):
    """반복 가능성이 있는 대문자 약어 토큰을 뽑는다(스톱워드 제외)."""
    return [token for token in CAPS_PATTERN.findall(text) if token not in STOPWORDS]


def detect_candidates(documents, known=None):
    """문서들에서 약어 후보를 집계한다.

    documents: {doc_id: 본문}
    known: 이미 사전에 있는 표기(제외 대상)
    반환: {surface: {surface, canonical, hint, count, seen_in}} (빈도 내림차순)
    """
    known = {k.lower() for k in (known or set())}
    candidates = {}

    def touch(surface, doc_id, hint=""):
        key = surface.lower()
        if key in known:
            return
        entry = candidates.setdefault(
            surface,
            {"surface": surface, "canonical": "", "hint": "", "count": 0, "seen_in": []},
        )
        entry["count"] += 1
        if hint and not entry["hint"]:
            entry["hint"] = hint
        if doc_id not in entry["seen_in"]:
            entry["seen_in"].append(doc_id)

    for doc_id, text in documents.items():
        for surface, hint in find_defined_abbreviations(text):
            touch(surface, doc_id, hint)
        for token in find_caps_tokens(text):
            touch(token, doc_id)

    return dict(sorted(candidates.items(), key=lambda kv: kv[1]["count"], reverse=True))


def _load_markdown_docs():
    docs = {}
    for source_dir in SOURCE_DIRS:
        if not source_dir.is_dir():
            continue
        for path in sorted(source_dir.glob("*.md")):
            if path.is_symlink():
                continue
            text = path.read_text(encoding="utf-8")
            if text.strip():
                docs[path.relative_to(DATA_DIR).with_suffix("").as_posix()] = text
    return docs


def main():
    documents = _load_markdown_docs()
    if not documents:
        print("스캔할 .md 문서가 없습니다. data/public/ 또는 data/private/ 에 문서를 넣으세요.")
        return

    known = set(build_alias_map().keys())
    candidates = detect_candidates(documents, known=known)
    payload = list(candidates.values())

    header = (
        "# 자동 탐지된 약어 후보 — 검토 후 data/private/aliases.yaml 로 옮기세요.\n"
        "# - canonical(정식명칭)을 채우면 확정, 약어가 아니면 그 항목을 지우세요.\n"
        "# - 이미 사전에 있는 표기는 제외됩니다.\n\n"
    )
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES_PATH.write_text(
        header + yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    print(f"문서 {len(documents)}개 스캔 -> 후보 {len(payload)}개")
    print(f"생성: {CANDIDATES_PATH}")
    print()
    for entry in payload[:20]:
        hint = f"  (힌트: {entry['hint']})" if entry["hint"] else ""
        print(f"- {entry['surface']}  x{entry['count']}{hint}")


if __name__ == "__main__":
    main()
