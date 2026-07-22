from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

from app.core.config import Settings
from app.core.database_migration import (
    TargetDatabaseNotEmpty,
    migrate_tables,
    rotate_encrypted_payload,
)
from app.core.secrets import SecretBox


def _box(*, field_key: str = "") -> SecretBox:
    return SecretBox(
        Settings(
            app_env="test",
            app_name="live-ops-dashboard",
            field_encryption_key=field_key,
        )
    )


def test_rotate_encrypted_payload_reencrypts_authenticated_values_only() -> None:
    old_box = _box()
    new_box = _box(field_key="production-field-key-with-at-least-32-characters")
    payload = {
        "access_token": old_box.encrypt("access-secret"),
        "refresh_token": old_box.encrypt("refresh-secret"),
        "scope": "offline_access bitable:app",
        "access_expires_at": "2026-07-20T15:24:11+00:00",
        "nested": [old_box.encrypt("nested-secret"), "plain-value", None],
    }

    rotated, count = rotate_encrypted_payload(payload, old_box=old_box, new_box=new_box)

    assert count == 3
    assert new_box.decrypt(rotated["access_token"]) == "access-secret"
    assert new_box.decrypt(rotated["refresh_token"]) == "refresh-secret"
    assert new_box.decrypt(rotated["nested"][0]) == "nested-secret"
    assert old_box.decrypt(rotated["access_token"]) is None
    assert rotated["scope"] == payload["scope"]
    assert rotated["access_expires_at"] == payload["access_expires_at"]
    assert rotated["nested"][1:] == ["plain-value", None]
    assert payload["access_token"] != rotated["access_token"]


def _migration_metadata() -> sa.MetaData:
    metadata = sa.MetaData()
    sa.Table(
        "rooms",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
    )
    sa.Table(
        "system_settings",
        metadata,
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("encrypted", sa.Boolean, nullable=False),
    )
    return metadata


def test_migrate_tables_refuses_to_overwrite_nonempty_target(tmp_path: Path) -> None:
    metadata = _migration_metadata()
    source = sa.create_engine(f"sqlite+pysqlite:///{tmp_path / 'source.db'}")
    target = sa.create_engine(f"sqlite+pysqlite:///{tmp_path / 'target.db'}")
    metadata.create_all(source)
    metadata.create_all(target)
    rooms = metadata.tables["rooms"]
    with target.begin() as connection:
        connection.execute(rooms.insert().values(id=1, name="existing"))

    with pytest.raises(TargetDatabaseNotEmpty, match="rooms=1"):
        migrate_tables(
            source_engine=source,
            target_engine=target,
            metadata=metadata,
            old_box=_box(),
            new_box=_box(field_key="production-field-key-with-at-least-32-characters"),
        )


def test_migrate_tables_replaces_target_and_rotates_encrypted_settings(tmp_path: Path) -> None:
    metadata = _migration_metadata()
    source = sa.create_engine(f"sqlite+pysqlite:///{tmp_path / 'source.db'}")
    target = sa.create_engine(f"sqlite+pysqlite:///{tmp_path / 'target.db'}")
    metadata.create_all(source)
    metadata.create_all(target)
    rooms = metadata.tables["rooms"]
    settings = metadata.tables["system_settings"]
    old_box = _box()
    new_box = _box(field_key="production-field-key-with-at-least-32-characters")
    with source.begin() as connection:
        connection.execute(
            rooms.insert(),
            [{"id": 1, "name": "一号直播间"}, {"id": 2, "name": "二号直播间"}],
        )
        connection.execute(
            settings.insert().values(
                key="feishu_user_oauth",
                value={
                    "access_token": old_box.encrypt("access-secret"),
                    "scope": "offline_access",
                },
                encrypted=True,
            )
        )
    with target.begin() as connection:
        connection.execute(rooms.insert().values(id=99, name="stale"))

    report = migrate_tables(
        source_engine=source,
        target_engine=target,
        metadata=metadata,
        old_box=old_box,
        new_box=new_box,
        replace_target=True,
    )

    with target.connect() as connection:
        migrated_rooms = connection.execute(sa.select(rooms).order_by(rooms.c.id)).mappings().all()
        migrated_setting = connection.execute(sa.select(settings)).mappings().one()
    assert [dict(row) for row in migrated_rooms] == [
        {"id": 1, "name": "一号直播间"},
        {"id": 2, "name": "二号直播间"},
    ]
    assert new_box.decrypt(migrated_setting["value"]["access_token"]) == "access-secret"
    assert old_box.decrypt(migrated_setting["value"]["access_token"]) is None
    assert migrated_setting["value"]["scope"] == "offline_access"
    assert report.source_counts == {"rooms": 2, "system_settings": 1}
    assert report.target_counts == report.source_counts
    assert report.rotated_secret_values == 1
    assert report.primary_key_digests["rooms"]
