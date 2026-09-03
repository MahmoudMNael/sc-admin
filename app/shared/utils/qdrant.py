import uuid

QDRANT_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "sc.qdrant")


def generate_qdrant_point_id(entry: dict) -> str:
    """Stable UUID v5 from immutable identity fields — never from a client-supplied id.

    Canonical key: standard_code|version_year|category_table_number|ref_number
    Activity, parameters, and searchable_text are attributes, not identity.
    """
    metadata = entry["standard_metadata"]
    hierarchy = entry["hierarchy"]
    canonical_key = "|".join(
        [
            metadata["standard_code"].strip(),
            metadata["version_year"].strip(),
            hierarchy["category_table_number"].strip(),
            hierarchy["ref_number"].strip(),
        ]
    )
    return str(uuid.uuid5(QDRANT_NAMESPACE, canonical_key))
