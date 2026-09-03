from app.shared.utils import generate_qdrant_point_id


def _entry(code="prEN 12464-1", year="2019", table="6.1", ref="6.1.3.1", **extra) -> dict:
    return {
        "standard_metadata": {"standard_code": code, "version_year": year, "is_latest": True},
        "hierarchy": {
            "category_table_number": table,
            "category_title": "Indoor",
            "ref_number": ref,
            "page": 1,
        },
        **extra,
    }


def test_same_identity_is_stable():
    first = generate_qdrant_point_id(_entry())
    second = generate_qdrant_point_id(_entry())
    assert first == second
    assert first.count("-") == 4


def test_concat_collision_is_not_a_collision():
    left = generate_qdrant_point_id(_entry(table="6.1", ref="6.1.3.1"))
    right = generate_qdrant_point_id(_entry(table="6.13", ref="6.13.1"))
    assert left != right


def test_strips_whitespace():
    padded = generate_qdrant_point_id(_entry(code="  prEN 12464-1  ", ref=" 6.1.3.1 "))
    plain = generate_qdrant_point_id(_entry())
    assert padded == plain


def test_activity_is_not_identity():
    left = generate_qdrant_point_id(_entry(activity="Parking"))
    right = generate_qdrant_point_id(_entry(activity="Corridors"))
    assert left == right
