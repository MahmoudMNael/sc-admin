from typing import Any

from .base import Specification


class MatchAllSpecification(Specification):
    """No-op specification — matches every record. The identity element for
    folding a dynamic list of optional filters with `&`."""

    def to_sql(self, model) -> Any:
        from sqlalchemy import true

        return true()

    def to_mongo(self, model) -> dict:
        return {}
