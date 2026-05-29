"""路径解析：分离只读资源（bundled）与用户数据（可写）。L0。

打包发布模式（PyInstaller --onefile）：
  - bundled_path("content/foo.json") → sys._MEIPASS/content/foo.json（只读，临时解压目录）
  - user_data_dir() → ~/.ming_sim/（跨进程持久，user 可写）

源码开发模式：
  - bundled_path("content/foo.json") → <repo>/content/foo.json
  - user_data_dir() → <repo>/data/（沿用旧布局）

判依据：sys.frozen 由 PyInstaller 注入。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import re


def is_frozen() -> bool:
    """是否在 PyInstaller 打包产物里跑。"""
    return getattr(sys, "frozen", False)


def bundled_root() -> Path:
    """只读资源根目录。
    frozen：PyInstaller 解压临时目录 _MEIPASS。
    源码：仓库根（ming_sim/ 父目录）。"""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)))
    return Path(__file__).resolve().parent.parent


def bundled_path(*parts: str) -> str:
    """拼 bundled 资源路径。例：bundled_path('content', 'events.json')。"""
    return str(bundled_root().joinpath(*parts))


def user_data_dir() -> Path:
    """用户可写数据目录。
    frozen：~/.ming_sim/（首次自动建）。
    源码：<repo>/data/（沿用旧布局，便于开发期切换存档）。
    环境变量 MING_SIM_DATA_DIR 可覆盖（用于容器部署挂载持久卷）。"""
    env_dir = os.environ.get("MING_SIM_DATA_DIR", "").strip()
    if env_dir:
        d = Path(env_dir)
    elif is_frozen():
        d = Path.home() / ".ming_sim"
    else:
        d = Path(__file__).resolve().parent.parent / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_data_path(*parts: str) -> str:
    """拼 user data 路径，自动建父目录。例：user_data_path('saves', 'auto.db')。"""
    p = user_data_dir().joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def scoped_user_id(raw_user_id: str) -> str:
    """把外部 user_id 规整为可安全落盘的目录名。

    假设输入为 Supabase UUID 格式（如 550e8400-e29b-41d4-a716-446655440000），
    经过此函数后保持不变。非 UUID 格式的 ID 中特殊字符会被替换为下划线，
    理论上存在碰撞风险，但当前系统只使用 UUID。
    """
    raw = (raw_user_id or "").strip().lower()
    if not raw:
        return "anonymous"
    return re.sub(r"[^a-z0-9._-]", "_", raw)


def user_scope_dir(user_id: str) -> Path:
    d = user_data_dir() / "users" / scoped_user_id(user_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def user_scope_path(user_id: str, *parts: str) -> str:
    p = user_scope_dir(user_id).joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def saves_dir_from_db_path(db_path: str) -> str:
    """与主库同级的 saves/ 目录（多用户隔离自动存档）。"""
    d = Path(db_path).resolve().parent / "saves"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)
