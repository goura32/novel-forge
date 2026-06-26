"""NovelForge engine package — split from monolithic engine.py."""

from .base import NovelEngineBase
from .design import DesignMixin
from .export import ExportMixin
from .plan import PlanMixin
from .write import WriteMixin


class NovelEngine(
    NovelEngineBase,
    PlanMixin,
    DesignMixin,
    WriteMixin,
    ExportMixin,
):
    """NovelEngine — combines base + plan + design + write + export mixins."""

    pass


__all__ = ["NovelEngine"]
