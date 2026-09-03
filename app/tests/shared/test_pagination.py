from app.shared.dto.pagination import PaginationMeta, PaginationQuery


def test_pagination_query_skip():
    assert PaginationQuery(page=1, limit=2).skip == 0
    assert PaginationQuery(page=2, limit=2).skip == 2


def test_pagination_meta_from_query():
    meta = PaginationMeta.from_query(total_count=100, page=1, limit=2)
    assert meta.model_dump() == {
        "total_count": 100,
        "page_size": 2,
        "current_page": 1,
        "total_pages": 50,
    }
    empty = PaginationMeta.from_query(total_count=0, page=1, limit=100)
    assert empty.total_pages == 0
