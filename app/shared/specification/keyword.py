import re
from typing import Literal

from .base import Specification


class KeywordSpecification(Specification):
    """Match entities where keywords appear (case-insensitive, partial match)
    across a fixed set of fields. `match_mode="any"`: at least one keyword
    hits at least one field. `match_mode="all"`: every keyword must hit at
    least one field (typical for multi-word queries)."""

    def __init__(self, fields: list[str], keywords: list[str], match_mode: Literal["any", "all"] = "any"):
        if not fields:
            raise ValueError("KeywordSpecification requires at least one field")
        self.fields = fields
        self.keywords = [kw.strip() for kw in keywords if kw and kw.strip()]
        self.match_mode = match_mode

    def to_sql(self, model):
        from sqlalchemy import and_, or_, true

        if not self.keywords:
            return true()
        per_keyword = [
            or_(*[getattr(model, field).ilike(self._ilike_pattern(kw), escape="\\") for field in self.fields])
            for kw in self.keywords
        ]
        return and_(*per_keyword) if self.match_mode == "all" else or_(*per_keyword)

    def to_mongo(self, model):
        if not self.keywords:
            return {}
        # ponytail: $regex collection scans; swap internals for $text once a text index exists.
        per_keyword = [
            {"$or": [{field: {"$regex": re.escape(kw), "$options": "i"}} for field in self.fields]}
            for kw in self.keywords
        ]
        return {"$and": per_keyword} if self.match_mode == "all" else {"$or": per_keyword}

    @staticmethod
    def _ilike_pattern(keyword: str) -> str:
        escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"
