from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

ModelT = TypeVar("ModelT")


class Specification(ABC, Generic[ModelT]):
    @abstractmethod
    def to_sql(self, model: type[ModelT]) -> Any:
        """Return a SQLAlchemy boolean expression, usable in .where(...)."""

    @abstractmethod
    def to_mongo(self, model: type[ModelT]) -> dict:
        """Return a MongoDB filter dict, usable in Model.find(...)."""

    def __and__(self, other: "Specification") -> "AndSpecification":
        return AndSpecification(self, other)

    def __or__(self, other: "Specification") -> "OrSpecification":
        return OrSpecification(self, other)

    def __invert__(self) -> "NotSpecification":
        return NotSpecification(self)


class AndSpecification(Specification):
    def __init__(self, *specs: Specification):
        self.specs = specs

    def to_sql(self, model):
        from sqlalchemy import and_

        return and_(*[s.to_sql(model) for s in self.specs])

    def to_mongo(self, model):
        return {"$and": [s.to_mongo(model) for s in self.specs]}


class OrSpecification(Specification):
    def __init__(self, *specs: Specification):
        self.specs = specs

    def to_sql(self, model):
        from sqlalchemy import or_

        return or_(*[s.to_sql(model) for s in self.specs])

    def to_mongo(self, model):
        return {"$or": [s.to_mongo(model) for s in self.specs]}


class NotSpecification(Specification):
    def __init__(self, spec: Specification):
        self.spec = spec

    def to_sql(self, model):
        from sqlalchemy import not_

        return not_(self.spec.to_sql(model))

    def to_mongo(self, model):
        return {"$nor": [self.spec.to_mongo(model)]}
