from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.runtime_settings import load_runtime_settings
from app.db.base import Base
from app.db.session import get_engine
from app.services.seed_service import seed_reference_data

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    engine = get_engine()
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        settings = load_runtime_settings(session)
        seed_reference_data(
            session,
            ROOT,
            get_settings().dev_admin_email,
            include_permission_test_accounts=True,
            default_feishu_chat_id=settings.feishu_bot_chat_id,
        )
    print("已初始化 46 个指标、5 个明确班次、五类业务角色、权限范围和测试账号。")


if __name__ == "__main__":
    main()
