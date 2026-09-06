from app.shared.specification.fields import ArrayContains, FieldEquals
from app.shared.specification.keyword import KeywordSpecification
from app.shared.specification.match_all import MatchAllSpecification


def test_keyword_spec_requires_fields():
    try:
        KeywordSpecification(fields=[], keywords=["x"])
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_keyword_spec_escapes_regex_and_composes():
    spec = KeywordSpecification(
        fields=["searchable_text", "activity"],
        keywords=["foo", "bar.baz"],
        match_mode="all",
    )
    query = spec.to_mongo(object)
    assert "$and" in query
    assert query["$and"][1]["$or"][0]["searchable_text"]["$regex"] == r"bar\.baz"
    assert query["$and"][0]["$or"][0]["searchable_text"]["$options"] == "i"


def test_match_all_and_field_equals_mongo():
    spec = MatchAllSpecification() & FieldEquals("activity", "Parking areas")
    query = spec.to_mongo(object)
    assert query == {"$and": [{}, {"activity": "Parking areas"}]}


def test_empty_keywords_match_all():
    spec = KeywordSpecification(fields=["activity"], keywords=["  ", ""])
    assert spec.to_mongo(object) == {}


class _Col:
    def contains(self, value):
        return ("contains", value)


class _Model:
    applications = _Col()


def test_array_contains_sql_and_mongo():
    spec = ArrayContains("applications", "interior")
    assert spec.to_mongo(object) == {"applications": "interior"}
    assert spec.to_sql(_Model) == ("contains", ["interior"])
