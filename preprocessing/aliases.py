"""약어/동의어 사전 로더 + 정규화(normalize).

사내 고유 약어는 data/private/aliases.yaml(git 미추적)에, 공통 기술용어는
data/public/aliases.example.yaml(커밋)에 둔다. 둘을 합쳐 쓰며 private가 우선한다.

normalize()는 '표기 하나'를 정식명칭으로 통일한다.
  - 통째로 일치할 때만 바꾼다(부분일치 X). 예: "USRID"는 "SR"로 안 바뀐다.
  - 대소문자는 무시한다. 예: "K8S" -> "Kubernetes".
  - 사전에 없으면 원래 값을 그대로 돌려준다(양끝 공백만 제거).
"""
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PUBLIC_ALIASES = PROJECT_ROOT / "data" / "public" / "aliases.example.yaml"
PRIVATE_ALIASES = PROJECT_ROOT / "data" / "private" / "aliases.yaml"


def _load_file(path):
    path = Path(path)
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or []


def map_from_entries(entries):
    """[{canonical, aliases[]}] 목록 -> {표기(소문자): 정식명칭} 매핑."""
    mapping = {}
    for entry in entries or []:
        canonical = (entry.get("canonical") or "").strip()
        if not canonical:
            continue
        mapping[canonical.lower()] = canonical  # 정식명칭 자신도 대소문자 통일
        for alias in entry.get("aliases") or []:
            alias = (alias or "").strip()
            if alias:
                mapping[alias.lower()] = canonical
    return mapping


def build_alias_map(paths=None):
    """사전 파일들을 읽어 합친 매핑을 만든다(뒤 파일 우선 = private > public)."""
    if paths is None:
        paths = [PUBLIC_ALIASES, PRIVATE_ALIASES]
    mapping = {}
    for path in paths:
        mapping.update(map_from_entries(_load_file(path)))
    return mapping


_DEFAULT_MAP = None


def _default_map():
    global _DEFAULT_MAP
    if _DEFAULT_MAP is None:
        _DEFAULT_MAP = build_alias_map()
    return _DEFAULT_MAP


def normalize(value, alias_map=None):
    """표기 하나를 정식명칭으로 통일. 사전에 없으면 원래 값(양끝 공백만 제거)."""
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return stripped
    mapping = alias_map if alias_map is not None else _default_map()
    return mapping.get(stripped.lower(), stripped)
