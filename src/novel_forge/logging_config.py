"""ロギング設定。

- ログファイル: series_dir/novel_forge.log に全レベル出力
- stderr: WARNING 以上（verbose 時は DEBUG）
- フォーマット: [HH:MM:SS] [LEVEL] message
"""

from __future__ import annotations

import logging
import sys
import time as _time
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler

console = Console()
_start_time = _time.monotonic()


class ElapsedFormatter(logging.Formatter):
    """経過時間付きフォーマッタ。"""

    def format(self, record):
        elapsed = _time.monotonic() - _start_time
        record.elapsed = f"{int(elapsed // 60):02d}:{int(elapsed % 60):02d}"
        return super().format(record)


def setup_logging(
    log_file: Path | None = None,
    verbose: bool = False,
    log_level: str = "DEBUG",
) -> logging.Logger:
    logger = logging.getLogger("novel_forge")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    file_fmt = ElapsedFormatter(
        fmt="[%(elapsed)s] [%(levelname)s] %(message)s",
    )
    stderr_fmt = logging.Formatter("[%(levelname)s] %(message)s")

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(log_file), encoding="utf-8")
        fh.setLevel(getattr(logging, log_level.upper(), logging.DEBUG))
        fh.setFormatter(file_fmt)
        logger.addHandler(fh)

    stderr_level = logging.DEBUG if verbose else logging.WARNING
    sh = logging.StreamHandler(sys.stderr)
    sh.setLevel(stderr_level)
    sh.setFormatter(stderr_fmt)
    logger.addHandler(sh)

    return logger


def get_logger(name: str = "novel_forge") -> logging.Logger:
    return logging.getLogger(name)
