from preprocessing.masking import mask_text

# 주의: 픽스처는 전부 가짜/문서용 더미값. 실제 사내 값(비밀번호·내부 IP·고객사 도메인) 금지.


def test_email_masked():
    assert mask_text("연락 user@example.com 참고") == "연락 [EMAIL] 참고"


def test_phone_masked():
    assert "[PHONE]" in mask_text("010-1234-5678")
    assert "[PHONE]" in mask_text("01012345678")
    assert "1234" not in mask_text("010-1234-5678")


def test_ipv4_masked():
    assert mask_text("접속 10.0.0.1 포트") == "접속 [IP] 포트"
    assert mask_text("192.0.2.1:30000") == "[IP]:30000"


def test_version_not_masked():
    # 버전번호(3파트)는 IP로 오인하지 않는다
    assert mask_text("Contrabass 3.0.6 릴리스") == "Contrabass 3.0.6 릴리스"


def test_date_not_masked():
    assert "2026.07.13" in mask_text("작성 2026.07.13")


def test_password_flag_masked():
    out = mask_text("mysqldump -u dbuser -p'Fake!Pw#123'")
    assert "[SECRET]" in out
    assert "Fake" not in out


def test_kv_secret_masked():
    assert mask_text("token=abc123def") == "token=[SECRET]"
    assert "[SECRET]" in mask_text("password: mypass123")
    assert "mypass123" not in mask_text("password: mypass123")


def test_bearer_masked():
    assert "[SECRET]" in mask_text("Authorization: Bearer eyJhbGciOi")


def test_clean_text_unchanged():
    assert mask_text("Prometheus 설치 가이드입니다") == "Prometheus 설치 가이드입니다"


def test_empty():
    assert mask_text("") == ""
    assert mask_text(None) is None


def test_kv_prefixed_key_masked():
    assert mask_text("db_password=SuperSecret1") == "db_password=[SECRET]"
    assert "pw123" not in mask_text("SPRING_DATASOURCE_PASSWORD=pw123")


def test_password_long_flag_masked():
    assert "mypass" not in mask_text("mysql --password mypass")
    assert "mypass" not in mask_text("mysql --password=mypass")


def test_db_url_cred_masked():
    assert mask_text("mysql://dbuser:FakePw123@10.0.0.1:3306/db") == "mysql://[SECRET]@[IP]:3306/db"


def test_jwt_masked():
    assert "[SECRET]" in mask_text("token eyJabc.def123.ghi456")


def test_aws_key_masked():
    # AWS 공식 문서 예시 키(공개 더미)
    assert "[SECRET]" in mask_text("키 AKIAIOSFODNN7EXAMPLE 노출")


def test_basic_auth_masked():
    assert "[SECRET]" in mask_text("Authorization: Basic dXNlcjpwYXNz")
    assert "dXNlcjpwYXNz" not in mask_text("Authorization: Basic dXNlcjpwYXNz")


def test_phone_variants_masked():
    assert "[PHONE]" in mask_text("010.1234.5678")
    assert "[PHONE]" in mask_text("+82-10-1234-5678")
    assert "[PHONE]" in mask_text("02-1234-5678")


def test_masking_idempotent():
    once = mask_text("메일 a@b.com IP 10.0.0.1 password: pw123")
    assert mask_text(once) == once
