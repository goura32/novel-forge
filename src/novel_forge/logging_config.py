"""ロギング設定。

- ログファイル: workdir/novel_forge.log に全レベル出力
- stderr: WARNING 以上（verbose 時は DEBUG）
- フォーマット: [YYYY-MM-DD HH:MM:SS] [series:X] [PID XXXX] [LEVEL] message
- マルチプロセス対応: 各プロセスが異なる slug でログを区別できる
"""

from __future__ import annotations

import logging
import os
import sys
import time as _time
from pathlib import Path

from rich.console import Console

console = Console()
_PID = os.getpid()


class ContextFormatter(logging.Formatter):
    """現在時刻 + PID + slug 付きフォーマッタ。"""

    pid: int | str = "?"
    series: str = ""

    def format(self, record):
        record.elapsed = _time.strftime("%Y-%m-%d %H:%M:%S")
        record.pid = self.pid
        record.series = self.series
        return super().format(record)


_context: dict[str, object] = {}


def setup_logging(
    log_file: Path | None = None,
    verbose: bool = False,
    log_level: str = "DEBUG",
    series_slug: str = "",
) -> logging.Logger:
    logger = logging.getLogger("novel_forge")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    fmt = "[%(elapsed)s]%(series)s [PID %(pid)d] [%(levelname)s] %(message)s"
    file_fmt = ContextFormatter(fmt=fmt)
    file_fmt.pid = _PID
    file_fmt.series = f" [{series_slug}]" if series_slug else ""

    stderr_fmt = ContextFormatter(fmt="[PID %(pid)d] [%(levelname)s] %(message)s")
    stderr_fmt.pid = _PID
    stderr_fmt.series = f" [{series_slug}]" if series_slug else ""

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(str(log_file), mode="a", encoding="utf-8")
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
