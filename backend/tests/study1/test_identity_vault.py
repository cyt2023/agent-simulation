import json

from cryptography.fernet import Fernet


def test_identity_value_is_encrypted_and_absent_from_analysis_export():
    from study1.identity_vault import IdentityVault, InMemoryIdentityVaultStore

    vault = IdentityVault(
        store=InMemoryIdentityVaultStore(),
        fernet_key=Fernet.generate_key(),
    )

    vault.store(
        pseudo_id="pseudo-1",
        identity_value="external-subject-7",
        session_id="session-1",
        role="principal",
        identity_kind="recruitment_id",
    )

    raw = vault.raw_row("pseudo-1")
    assert b"external-subject-7" not in raw.encrypted_value

    analysis_text = json.dumps(vault.analysis_export_rows(), ensure_ascii=False)
    assert "external-subject-7" not in analysis_text
    assert "pseudo-1" in analysis_text


def test_identity_vault_rejects_missing_or_invalid_key():
    from study1.identity_vault import IdentityVault, IdentityVaultError

    try:
        IdentityVault(fernet_key=b"not-a-fernet-key")
    except IdentityVaultError as error:
        assert error.code == "INVALID_VAULT_KEY"
    else:
        raise AssertionError("invalid vault keys must fail closed")
