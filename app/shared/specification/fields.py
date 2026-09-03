from typing import Any

from .base import Specification


class FieldEquals(Specification):
    """Exact-match filter. `field` may be a dotted path for nested Mongo
    documents (e.g. "standard_metadata.standard_code")."""

    def __init__(self, field: str, value: Any):
        self.field = field
        self.value = value

    def to_sql(self, model):
        return getattr(model, self.field) == self.value

    def to_mongo(self, model):
        return {self.field: self.value}
