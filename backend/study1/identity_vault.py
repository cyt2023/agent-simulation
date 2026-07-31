"""Encrypted Study 1 identity vault.

The analysis database should only know pseudonymous participant identifiers.
Recruitment IDs, emails, platform worker IDs, or any other direct identifiers
belong in this vault, which can be backed by a separate database URL and is
encrypted before persistence.
"""

from __future__ import annotations

import base64
import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import DateTime, LargeBinary, String, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class IdentityVaultError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class IdentityVaultBase(DeclarativeBase):
    pass


@dataclass(frozen=True)
class IdentityVaultRecord:
    pseudo_id: str
    session_id: str
    role: str
    identity_kind: str
    encrypted_value: bytes
    created_at: datetime
    updated_at: datetime

    def analysis_row(self) -> dict[str, object]:
        return {
            "pseudo_id": self.pseudo_id,
            "session_id": self.session_id,
            "role": self.role,
            "identity_kind": self.identity_kind,
            "vault_ciphertext_checksum": hashlib.sha256(
                self.encrypted_value
            ).hexdigest(),
            "created_at": self.created_at.isoformat().replace("+00:00", "Z"),
            "updated_at": self.updated_at.isoformat().replace("+00:00", "Z"),
        }


class IdentityVaultRow(IdentityVaultBase):
    __tablename__ = "study1_identity_vault"

    pseudo_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    identity_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_value: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class IdentityVaultStore(Protocol):
    def upsert(self, record: IdentityVaultRecord) -> IdentityVaultRecord: ...

    def get(self, pseudo_id: str) -> IdentityVaultRecord | None: ...

    def list(self) -> list[IdentityVaultRecord]: ...

    def delete(self, pseudo_ids: list[str]) -> int: ...


class InMemoryIdentityVaultStore:
    def __init__(self):
        self.rows: dict[str, IdentityVaultRecord] = {}

    def upsert(self, record: IdentityVaultRecord) -> IdentityVaultRecord:
        self.rows[record.pseudo_id] = record
        return record

    def get(self, pseudo_id: str) -> IdentityVaultRecord | None:
        return self.rows.get(pseudo_id)

    def list(self) -> list[IdentityVaultRecord]:
        return list(self.rows.values())

    def delete(self, pseudo_ids: list[str]) -> int:
        count = 0
        for pseudo_id in pseudo_ids:
            if pseudo_id in self.rows:
                count += 1
                del self.rows[pseudo_id]
        return count


class SqlAlchemyIdentityVaultStore:
    """A small dedicated store for direct identifiers.

    It intentionally does not reuse the main Study 1 SQLAlchemy metadata. That
    keeps direct identity lookup tables physically separable when
    ``STUDY1_IDENTITY_DATABASE_URL`` points to a distinct database.
    """

    def __init__(self, database_url: str):
        if not database_url:
            raise IdentityVaultError(
                "IDENTITY_DATABASE_REQUIRED",
                "STUDY1_IDENTITY_DATABASE_URL is required for the identity vault",
            )
        kwargs = {"pool_pre_ping": True}
        if database_url.startswith("sqlite"):
            kwargs.update(
                {
                    "connect_args": {"check_same_thread": False},
                    "poolclass": StaticPool,
                }
            )
        self.engine = create_engine(database_url, **kwargs)
        IdentityVaultBase.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def upsert(self, record: IdentityVaultRecord) -> IdentityVaultRecord:
        with self.SessionLocal.begin() as session:
            row = session.get(IdentityVaultRow, record.pseudo_id)
            if row is None:
                row = IdentityVaultRow(
                    pseudo_id=record.pseudo_id,
                    session_id=record.session_id,
                    role=record.role,
                    identity_kind=record.identity_kind,
                    encrypted_value=record.encrypted_value,
                    created_at=record.created_at,
                    updated_at=record.updated_at,
                )
                session.add(row)
            else:
                row.session_id = record.session_id
                row.role = record.role
                row.identity_kind = record.identity_kind
                row.encrypted_value = record.encrypted_value
                row.updated_at = record.updated_at
            return _row_to_record(row)

    def get(self, pseudo_id: str) -> IdentityVaultRecord | None:
        with self.SessionLocal() as session:
            row = session.get(IdentityVaultRow, pseudo_id)
            return _row_to_record(row) if row else None

    def list(self) -> list[IdentityVaultRecord]:
        with self.SessionLocal() as session:
            return [
                _row_to_record(row)
                for row in session.scalars(
                    select(IdentityVaultRow).order_by(IdentityVaultRow.created_at)
                )
            ]

    def delete(self, pseudo_ids: list[str]) -> int:
        with self.SessionLocal.begin() as session:
            count = 0
            for pseudo_id in pseudo_ids:
                row = session.get(IdentityVaultRow, pseudo_id)
                if row:
                    count += 1
                    session.delete(row)
            return count


def _row_to_record(row: IdentityVaultRow) -> IdentityVaultRecord:
    return IdentityVaultRecord(
        pseudo_id=row.pseudo_id,
        session_id=row.session_id,
        role=row.role,
        identity_kind=row.identity_kind,
        encrypted_value=row.encrypted_value,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class IdentityVault:
    def __init__(
        self,
        *,
        fernet_key: bytes | str,
        store: IdentityVaultStore | None = None,
        database_url: str | None = None,
    ):
        try:
            if isinstance(fernet_key, str):
                fernet_key = fernet_key.encode("utf-8")
            # Construct Fernet eagerly so invalid keys fail closed.
            self.fernet = Fernet(fernet_key)
        except (ValueError, TypeError, base64.binascii.Error) as error:
            raise IdentityVaultError("INVALID_VAULT_KEY", "Invalid STUDY1_VAULT_KEY") from error
        self.store_backend = store or SqlAlchemyIdentityVaultStore(database_url or "")

    @classmethod
    def from_env(cls) -> "IdentityVault":
        key = os.environ.get("STUDY1_VAULT_KEY", "")
        if not key:
            raise IdentityVaultError(
                "VAULT_KEY_REQUIRED", "STUDY1_VAULT_KEY is required"
            )
        return cls(
            fernet_key=key,
            database_url=os.environ.get("STUDY1_IDENTITY_DATABASE_URL", ""),
        )

    def store(
        self,
        *,
        pseudo_id: str,
        identity_value: str,
        session_id: str,
        role: str,
        identity_kind: str,
    ) -> IdentityVaultRecord:
        if not pseudo_id or not identity_value:
            raise IdentityVaultError(
                "IDENTITY_VALUE_REQUIRED", "pseudo_id and identity_value are required"
            )
        now = _utcnow()
        existing = self.store_backend.get(pseudo_id)
        encrypted_value = self.fernet.encrypt(identity_value.encode("utf-8"))
        return self.store_backend.upsert(
            IdentityVaultRecord(
                pseudo_id=pseudo_id,
                session_id=session_id,
                role=role,
                identity_kind=identity_kind,
                encrypted_value=encrypted_value,
                created_at=existing.created_at if existing else now,
                updated_at=now,
            )
        )

    def reveal(self, pseudo_id: str) -> str:
        row = self.raw_row(pseudo_id)
        try:
            return self.fernet.decrypt(row.encrypted_value).decode("utf-8")
        except InvalidToken as error:
            raise IdentityVaultError("VAULT_DECRYPTION_FAILED", "Unable to decrypt identity") from error

    def raw_row(self, pseudo_id: str) -> IdentityVaultRecord:
        row = self.store_backend.get(pseudo_id)
        if row is None:
            raise IdentityVaultError("IDENTITY_NOT_FOUND", "Identity record not found")
        return row

    def analysis_export_rows(self) -> list[dict[str, object]]:
        return [row.analysis_row() for row in self.store_backend.list()]

    def delete_pseudo_ids(self, pseudo_ids: list[str]) -> int:
        return self.store_backend.delete(pseudo_ids)
