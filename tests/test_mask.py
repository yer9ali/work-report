from mask import mask_secrets


def test_password_elements_are_masked_whatever_the_prefix() -> None:
    text = "<sender><password>Pa55word!</password></sender><ns:password a='1'>x\ny</ns:password>"

    assert mask_secrets(text) == (
        "<sender><password>***</password></sender><ns:password a='1'>***</ns:password>"
    )


def test_key_value_secrets_are_masked() -> None:
    text = (
        "X-Internal-Token: FAKEtok3nVALUE/xyz\n"
        "password=hunter2&user=a\n"
        '{"token": "abc.def", "secret":"s3"}\n'
        "Authorization: Bearer eyJhbGciOi.payload"
    )

    masked = mask_secrets(text)

    for secret in ("FAKEtok3nVALUE", "hunter2", "abc.def", "s3", "eyJhbGciOi"):
        assert secret not in masked
    assert "user=a" in masked


def test_long_base64_is_replaced_by_its_size() -> None:
    blob = "A" * 400

    assert mask_secrets(f"<data>{blob}</data>") == "<data>[base64 300 байт]</data>"


def test_ordinary_text_is_untouched() -> None:
    text = "Заказ оформлен, номер 100200300400, max tokens left"

    assert mask_secrets(text) == text


def test_prefixed_key_names_are_masked() -> None:
    text = (
        "DB_PASSWORD=abc123\n"
        "my_password=xyz789\n"
        "access_token=secret1\n"
        "refresh_token: secret2\n"
        "client_secret=secret3\n"
        "x-api-key: secret4\n"
        "max tokens left"
    )

    masked = mask_secrets(text)

    for secret in ("abc123", "xyz789", "secret1", "secret2", "secret3", "secret4"):
        assert secret not in masked, f"Secret '{secret}' not masked in: {masked}"
    assert "max tokens left" in masked


def test_authorization_with_any_scheme_is_masked() -> None:
    text = (
        "Authorization: Bearer eyJhbGciOi.payload\n"
        "Authorization: Basic dXNlcjpwYXNz\n"
        "Authorization: Token abc123xyz\n"
        "Authorization: Custom credential456"
    )

    masked = mask_secrets(text)

    for secret in ("eyJhbGciOi", "dXNlcjpwYXNz", "abc123xyz", "credential456"):
        assert secret not in masked, f"Secret '{secret}' not masked in: {masked}"


def test_escaped_quotes_in_values_are_masked() -> None:
    text = 'password: "a\\"b-secret"'

    masked = mask_secrets(text)

    assert "b-secret" not in masked
    assert "a\\" not in masked or "***" in masked


def test_bare_bearer_token_without_key_is_masked() -> None:
    text = "curl -H 'Authorization: Bearer token123xyz' http://example.com"

    masked = mask_secrets(text)

    assert "token123xyz" not in masked


def test_url_userinfo_is_masked() -> None:
    text = "https://user:password123@example.com/path"

    masked = mask_secrets(text)

    assert "password123" not in masked
    assert "user:***@" in masked or "user:***@example.com" in masked


def test_bare_bearer_token_truly_bare() -> None:
    text = 'curl -H "x" --url example.com Bearer abc.def.ghi1234'

    masked = mask_secrets(text)

    assert "abc.def.ghi1234" not in masked
    assert "Bearer ***" in masked


def test_value_pattern_does_not_swallow_second_word() -> None:
    text = "token: abc and then more words\ntokens: 5 of 10 used\npassword=secret next line"

    masked = mask_secrets(text)

    # Only the first token after separator should be masked
    assert "and then more words" in masked
    assert "of 10 used" in masked
    assert "next line" in masked
    # Secrets should be masked
    assert "abc and" not in masked
    assert "secret next" not in masked


def test_token_value_preserves_spacing() -> None:
    text = "token: abc"

    masked = mask_secrets(text)

    assert masked == "token: ***"


def test_exact_escaped_quote_masking() -> None:
    text = 'password: "a\\"b-secret"'

    masked = mask_secrets(text)

    assert masked == 'password: "***"'


def test_url_userinfo_does_not_match_port() -> None:
    text = "http://h:8080/a@b"

    masked = mask_secrets(text)

    # Port 8080 is not a password, should not be masked
    assert masked == "http://h:8080/a@b"


def test_url_userinfo_with_space_between_port_and_at() -> None:
    text = "http://x:80/ y@z"

    masked = mask_secrets(text)

    # 80 is a port, not password; should not match across space and @
    assert masked == "http://x:80/ y@z"


def test_authorization_can_have_scheme_word() -> None:
    text = "Authorization: Bearer token123xyz"

    masked = mask_secrets(text)

    assert masked == "Authorization: ***"
    assert "Bearer" not in masked or "Bearer ***" in masked
    assert "token123xyz" not in masked


def test_github_tokens_pem_keys_and_cookies_are_masked() -> None:
    pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\nIBAAK\n-----END RSA PRIVATE KEY-----"
    text = (
        "git clone with ghp_abcdefghijklmnopqrstuvwxyz0123456789 ok\n"
        "pat github_pat_11ABCDEFG0123456789_abcdefghijklmnop\n"
        f"{pem}\n"
        "Cookie: session=abc123; theme=dark\n"
        "set-cookie: sid=xyz789; Path=/\n"
    )

    masked = mask_secrets(text)

    for secret in ("ghp_abc", "github_pat_11", "MIIEow", "abc123", "xyz789"):
        assert secret not in masked, secret
    assert "git clone with *** ok" in masked
    assert "[private key]" in masked
    assert "Cookie: ***" in masked
