from __future__ import annotations

import os
from pathlib import Path


def project_root() -> Path:
    configured = os.getenv("PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    candidates = [Path.cwd(), *Path.cwd().parents, Path(__file__).resolve().parent]
    candidates.extend(Path(__file__).resolve().parents)
    for candidate in candidates:
        if (candidate / "config" / "metric_seed.yml").is_file():
            return candidate
    raise RuntimeError("找不到项目 config/metric_seed.yml；请设置 PROJECT_ROOT")
