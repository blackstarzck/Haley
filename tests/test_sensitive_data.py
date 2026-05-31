from haley.security import mask_sensitive_values


def test_mask_sensitive_values_redacts_secrets_recursively() -> None:
    value = {
        "access_key": "public-ish",
        "secret_key": "very-secret",
        "jwt": "token",
        "nonce": "nonce-value",
        "query_hash": "hash-value",
        "headers": {"Authorization": "Bearer token"},
        "nested": [{"api_secret": "hidden"}],
    }

    masked = mask_sensitive_values(value)

    assert masked == {
        "access_key": "public-ish",
        "secret_key": "[REDACTED]",
        "jwt": "[REDACTED]",
        "nonce": "[REDACTED]",
        "query_hash": "[REDACTED]",
        "headers": {"Authorization": "[REDACTED]"},
        "nested": [{"api_secret": "[REDACTED]"}],
    }


def test_mask_sensitive_values_does_not_mutate_original() -> None:
    value = {"secret_key": "very-secret"}

    mask_sensitive_values(value)

    assert value == {"secret_key": "very-secret"}
