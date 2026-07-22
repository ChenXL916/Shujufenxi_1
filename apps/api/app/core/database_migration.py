from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import TypeVar, cast

import sqlalchemy as sa
from sqlalchemy import Connection, Engine, MetaData, Table

from app.core.secrets import SecretBox

T = TypeVar("T")


class TargetDatabaseNotEmpty(RuntimeError):
    """Raised when a migration would overwrite existing target data."""


class MigrationVerificationError(RuntimeError):
    """Raised when target counts or primary keys differ from the source."""


@dataclass(frozen=True)
class MigrationReport:
    source_counts: dict[str, int]
    target_counts: dict[str, int]
    primary_key_digests: dict[str, str]
    rotated_secret_values: int


def _table_counts(connection: Connection, tables: list[Table]) -> dict[str, int]:
    return {
        table.name: int(
            connection.execute(sa.select(sa.func.count()).select_from(table)).scalar_one()
        )
        for table in tables
    }


def _primary_key_digest(connection: Connection, table: Table) -> str:
    columns = list(table.primary_key.columns)
    if not columns:
        return ""
    digest = hashlib.sha256()
    statement = sa.select(*columns).order_by(*columns)
    for row in connection.execute(statement):
        canonical = json.dumps(
            [str(value) if value is not None else None for value in row],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        digest.update(canonical.encode())
        digest.update(b"\n")
    return digest.hexdigest()


def _clear_target(connection: Connection, tables: list[Table]) -> None:
    if not tables:
        return
    if connection.dialect.name == "postgresql":
        preparer = connection.dialect.identifier_preparer
        names = ", ".join(preparer.quote(table.name) for table in tables)
        connection.exec_driver_sql(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE")
        return
    for table in reversed(tables):
        connection.execute(table.delete())


def migrate_tables(
    *,
    source_engine: Engine,
    target_engine: Engine,
    metadata: MetaData,
    old_box: SecretBox,
    new_box: SecretBox,
    replace_target: bool = False,
    batch_size: int = 500,
) -> MigrationReport:
    """Copy application tables atomically with fail-closed verification."""

    if batch_size < 1:
        raise ValueError("batch_size 必须大于 0")
    tables = list(metadata.sorted_tables)
    source_names = set(sa.inspect(source_engine).get_table_names())
    target_names = set(sa.inspect(target_engine).get_table_names())
    expected_names = {table.name for table in tables}
    missing_source = sorted(expected_names - source_names)
    missing_target = sorted(expected_names - target_names)
    if missing_source or missing_target:
        raise MigrationVerificationError(
            f"数据库结构不完整：source_missing={missing_source}, target_missing={missing_target}"
        )

    with source_engine.connect() as source, target_engine.begin() as target:
        existing_counts = _table_counts(target, tables)
        populated = {name: count for name, count in existing_counts.items() if count}
        if populated and not replace_target:
            details = ", ".join(f"{name}={count}" for name, count in populated.items())
            raise TargetDatabaseNotEmpty(f"目标数据库非空：{details}")
        if replace_target:
            _clear_target(target, tables)

        source_counts = _table_counts(source, tables)
        source_digests = {table.name: _primary_key_digest(source, table) for table in tables}
        rotated_secret_values = 0
        for table in tables:
            batch: list[dict[str, object]] = []
            for row in source.execute(sa.select(table)).mappings():
                item = dict(row)
                if (
                    table.name == "system_settings"
                    and bool(item.get("encrypted"))
                    and isinstance(item.get("value"), (dict, list))
                ):
                    item["value"], rotated = rotate_encrypted_payload(
                        item["value"], old_box=old_box, new_box=new_box
                    )
                    rotated_secret_values += rotated
                batch.append(item)
                if len(batch) >= batch_size:
                    target.execute(table.insert(), batch)
                    batch.clear()
            if batch:
                target.execute(table.insert(), batch)

        target_counts = _table_counts(target, tables)
        target_digests = {table.name: _primary_key_digest(target, table) for table in tables}
        if source_counts != target_counts:
            raise MigrationVerificationError(
                f"逐表行数不一致：source={source_counts}, target={target_counts}"
            )
        mismatched_digests = {
            name: {"source": source_digests[name], "target": target_digests[name]}
            for name in source_digests
            if source_digests[name] != target_digests[name]
        }
        if mismatched_digests:
            raise MigrationVerificationError(f"主键摘要不一致：{mismatched_digests}")

    return MigrationReport(
        source_counts=source_counts,
        target_counts=target_counts,
        primary_key_digests=target_digests,
        rotated_secret_values=rotated_secret_values,
    )


def rotate_encrypted_payload(  # noqa: UP047 - keep Python 3.11 tooling compatibility
    payload: T,
    *,
    old_box: SecretBox,
    new_box: SecretBox,
) -> tuple[T, int]:
    """Re-encrypt values authenticated by ``old_box`` while preserving JSON shape."""

    def rotate(value: object) -> tuple[object, int]:
        if isinstance(value, str):
            plaintext = old_box.decrypt(value)
            if plaintext is None:
                return value, 0
            return new_box.encrypt(plaintext), 1
        if isinstance(value, dict):
            output: dict[object, object] = {}
            rotated_count = 0
            for key, child in value.items():
                rotated_child, child_count = rotate(child)
                output[key] = rotated_child
                rotated_count += child_count
            return output, rotated_count
        if isinstance(value, list):
            output_list: list[object] = []
            rotated_count = 0
            for child in value:
                rotated_child, child_count = rotate(child)
                output_list.append(rotated_child)
                rotated_count += child_count
            return output_list, rotated_count
        if isinstance(value, tuple):
            output_tuple: list[object] = []
            rotated_count = 0
            for child in value:
                rotated_child, child_count = rotate(child)
                output_tuple.append(rotated_child)
                rotated_count += child_count
            return tuple(output_tuple), rotated_count
        return value, 0

    rotated, count = rotate(payload)
    return cast(T, rotated), count
