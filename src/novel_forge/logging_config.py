"""ロギング設定。

- stdout: rich.console.Console でユーザー向け進捗表示
- stderr: WARNING 以上（verbose 時は DEBUG）
- ログファイル: series_dir/novel_forge.log に全レベル出力
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import TextIO

from rich.console import Console
from rich.logging import RichHandler


console = Console()


def setup_logging(
    log_file: Path | None = None,
    verbose: bool = False,
) -> logging.Logger:
    """ロギングを設定する。

    Args:
        log_file: ログファイルパス。指定した場合のみファイルに記録。
        verbose: True の場合、stderr にもデバッグレベルで出力。

    Returns:
        設定済みのルートロガー。
    """
    logger = logging.getLogger("novel_forge")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    # フォーマッタ
    file_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    stderr_fmt = logging.Formatter("[%(levelname)s] %(message)s")

    # ハンドラ1: ログファイル（常に DEBUG 以上）
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(log_file), encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(file_fmt)
        logger.addHandler(fh)

    # ハンドラ2: stderr（WARNING 以上、verbose 時は DEBUG）
    stderr_level = logging.DEBUG if verbose else logging.WARNING
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(stderr_level)
    sh.setFormatter(stderr_fmt)
    logger.addHandler(sh)

    return logger


def get_logger(name: str = "novel_forge") -> logging.Logger:
    """名前付きロガーを取得する。"""
    return logging.getLogger(name)
