"""
<<<<<<< HEAD
アプリケーション設定管理

.env ファイルおよび環境変数を介して、パスやモデル名などの設定を制御する。
パスが相対パスで指定された場合、プロジェクトルートを基準として解決する。
=======
設定の窓口：.env とプロジェクト内パス。ここだけ見ればよい。

.env のパス: 相対パスなら project_root 基準、絶対パスならそのまま使う。
>>>>>>> ff96d51 (refactor: config単一ファイル化、eval改善)
"""

import os
from pathlib import Path

import dotenv

dotenv.load_dotenv()


def _resolve_path(env_value: str | None, default: Path) -> Path:
    """
    環境変数の値をパスとして解決する。
    相対パスの場合はプロジェクトルート基準、絶対パスの場合はそのまま使用する。
    未設定の場合はデフォルト値を返す。
    """

    project_root = Path(__file__).resolve().parents[2]

    if not env_value or not env_value.strip():
        return default
    path = Path(env_value.strip())
    return path if path.is_absolute() else (project_root / path).resolve()


# ---------------------------------------------------------------------------
# パス設定（環境変数で上書き可能。相対パスはプロジェクトルート基準）
# ---------------------------------------------------------------------------

DUCKDB_PATH = _resolve_path(
    os.getenv("SQL_AGENT_DUCKDB_PATH"),
    Path("duckdb") / "workspace.duckdb",
)
BIRD_PATH = _resolve_path(
    os.getenv("SQL_AGENT_BIRD_PATH"),
    Path("data") / "bird" / "minidev" / "MINIDEV",
)

# ---------------------------------------------------------------------------
# その他の設定（環境変数で上書き可能）
# ---------------------------------------------------------------------------

LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-pro")
DB_TYPE = os.getenv("SQL_AGENT_DB_TYPE", "bird")
