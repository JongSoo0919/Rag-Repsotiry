from preprocessing.aliases import map_from_entries, normalize

SAMPLE = [
    {"canonical": "Kubernetes", "aliases": ["k8s", "kube", "쿠버네티스"]},
    {"canonical": "Service Request", "aliases": ["SR"]},
]
MAP = map_from_entries(SAMPLE)


def test_alias_maps_to_canonical():
    assert normalize("k8s", MAP) == "Kubernetes"
    assert normalize("kube", MAP) == "Kubernetes"
    assert normalize("쿠버네티스", MAP) == "Kubernetes"


def test_case_insensitive():
    assert normalize("K8S", MAP) == "Kubernetes"
    assert normalize("Sr", MAP) == "Service Request"


def test_canonical_itself_normalizes():
    # 대소문자만 다른 정식명칭도 통일된다
    assert normalize("kubernetes", MAP) == "Kubernetes"


def test_unknown_passthrough():
    assert normalize("Service-JS", MAP) == "Service-JS"
    assert normalize("처음보는말", MAP) == "처음보는말"


def test_whole_value_only():
    # 약어가 다른 단어 '안에' 들어있어도 통째로 같지 않으면 안 바꾼다
    assert normalize("USRID", MAP) == "USRID"


def test_blank_and_none():
    assert normalize("  k8s  ", MAP) == "Kubernetes"  # 양끝 공백 무시
    assert normalize("", MAP) == ""
    assert normalize(None, MAP) is None


def test_private_overrides_public():
    entries = [
        {"canonical": "PublicName", "aliases": ["x"]},
        {"canonical": "PrivateName", "aliases": ["x"]},  # 뒤가 우선
    ]
    assert normalize("x", map_from_entries(entries)) == "PrivateName"
