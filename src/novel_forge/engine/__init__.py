"""NovelForge engine package — split from monolithic engine.py."""

from .base import NovelEngineBase
from .plan import PlanMixin
from .outline import OutlineMixin
from .write import WriteMixin
from .export import ExportMixin


# Combined class: MRO resolves NovelEngineBase first, then mixins
class NovelEngine(
    NovelEngineBase,
    PlanMixin,
    OutlineMixin,
    WriteMixin,
    ExportMixin,
):
    """NovelEngine — combines base + plan + outline + write + export mixins."""
    pass


__all__ = ["NovelEngine"]
