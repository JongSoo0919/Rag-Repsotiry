"""민감정보 마스킹 — 적재(load)·임포트 시점에 원문을 치환한다(결정론·정규식).

실제 Confluence 문서에서 발견된 유형 기준. 치환은 placeholder로(맥락은 남긴다).

한계(중요): 정규식 마스킹은 2차 방어선이다. 임의 형식 시크릿·사람 이름·비-IP
내부 호스트명·따옴표 없는 `-p<pw>`(docker `-p` 포트와 구분 불가)·다중단어 무따옴표
값 등은 구조적으로 못 잡는다. 1차 방어는 '민감 문서(space)를 애초에 넣지 않는 선택 제외'다.
"""
import re

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# 휴대폰: (선택 +82, 이때 앞 0 생략) 01x-xxxx-xxxx, 구분자 - . 공백
MOBILE = re.compile(r"(?:\+?82[-.\s]?)?0?1[016789][-.\s]?\d{3,4}[-.\s]?\d{4}")
# 유선: 02/0xx-xxx(x)-xxxx (구분자 필수 — 과잉매칭 방지)
LANDLINE = re.compile(r"\b0\d{1,2}[-.\s]\d{3,4}[-.\s]\d{4}\b")

# IPv4 4옥텟 (3파트 버전/날짜는 제외됨)
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")

# PEM 개인키 블록
PEM = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S)
# JWT
JWT = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+")
# AWS Access Key ID
AWS_KEY = re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")
# Authorization: Bearer/Basic <token>
AUTH_HEADER = re.compile(r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)[A-Za-z0-9._\-+/=]+")
# 단독 Bearer 토큰
BEARER = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{8,}")
# DB/서비스 URL 자격증명: scheme://user:pass@
DB_URL_CRED = re.compile(r"([A-Za-z][A-Za-z0-9+.\-]*://)[^:/\s@]+:[^@/\s]+@")
# 비밀번호 플래그: --password[= ]VALUE, -p'...'/-p"..." (무따옴표 -p는 docker 포트와 충돌 → 제외)
PW_LONG = re.compile(r"(?i)(--password[=\s]\s*)(?:'[^']*'|\"[^\"]*\"|[^\s'\"-]\S*)")
PW_SHORT_Q = re.compile(r"(-p\s*)(?:'[^']*'|\"[^\"]*\")")
# key=value / key: value 시크릿 (접두어 붙은 키 db_password 등 포함, 값은 따옴표 통째 또는 공백 전까지)
KV_SECRET = re.compile(
    r"(?i)([A-Za-z0-9_\-]*(?:password|passwd|pwd|secret|token|api[_-]?key|access[_-]?token))(\s*[:=]\s*)(?:'[^']*'|\"[^\"]*\"|\S+)"
)


def mask_text(text):
    """민감정보를 placeholder로 치환한 텍스트를 반환한다. 멱등(재적용 안전)."""
    if not text:
        return text
    text = PEM.sub("[SECRET]", text)
    text = JWT.sub("[SECRET]", text)
    text = AWS_KEY.sub("[SECRET]", text)
    text = AUTH_HEADER.sub(r"\1[SECRET]", text)
    text = BEARER.sub("[SECRET]", text)
    text = DB_URL_CRED.sub(r"\1[SECRET]@", text)
    text = PW_LONG.sub(r"\1[SECRET]", text)
    text = PW_SHORT_Q.sub(r"\1[SECRET]", text)
    text = KV_SECRET.sub(r"\1\2[SECRET]", text)
    text = EMAIL.sub("[EMAIL]", text)
    text = MOBILE.sub("[PHONE]", text)
    text = LANDLINE.sub("[PHONE]", text)
    text = IPV4.sub("[IP]", text)
    return text
