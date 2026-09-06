from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.fixtures.dto import (
    CreateVariantImageRequest,
    UpdateFixtureRequest,
    UpdateVariantRequest,
)
from app.tests.modules.fixtures.helpers import (
    fixture_payload,
    make_service,
    seed_asset,
    variant_payload,
)


async def test_create_fixture_requires_asset():
    service, _, _, _, _ = make_service()
    with pytest.raises(HTTPException) as exc:
        await service.create_fixture(fixture_payload(uuid4()))
    assert exc.value.status_code == 404


async def test_create_and_get_graph():
    service, assets, _, _, _ = make_service()
    ies = seed_asset(assets, "lamp.ies")
    model = seed_asset(assets, "lamp.glb")
    image = seed_asset(assets, "lamp.png")
    created = await service.create_fixture(fixture_payload(ies.id))
    variant = await service.create_variant(created.id, variant_payload(model_3d_file_id=model.id))
    await service.create_variant_image(created.id, variant.id, CreateVariantImageRequest(image_file_id=image.id))
    detail = await service.get_fixture(created.id)
    assert detail.name == "High Bay"
    assert detail.ies_file.original_filename == "lamp.ies"
    assert len(detail.variants) == 1
    assert detail.variants[0].model_3d_file.original_filename == "lamp.glb"
    assert detail.variants[0].images[0].image_file.original_filename == "lamp.png"


async def test_list_filters_keyword_application_and_flag():
    service, assets, _, _, _ = make_service()
    ies = seed_asset(assets)
    await service.create_fixture(fixture_payload(ies.id, name="High Bay", is_main_solution=True))
    await service.create_fixture(
        fixture_payload(ies.id, name="Flood", manufacturer_name="Other", applications=["industrial"])
    )
    items, total = await service.list_fixtures("high", None, None, skip=0, limit=10)
    assert total == 1
    assert items[0].name == "High Bay"
    industrial, n = await service.list_fixtures(None, "industrial", None, skip=0, limit=10)
    assert n == 1
    assert industrial[0].name == "Flood"
    mains, m = await service.list_fixtures(None, None, True, skip=0, limit=10)
    assert m == 1
    assert mains[0].is_main_solution is True


async def test_duplicate_variant_name_409():
    service, assets, _, _, _ = make_service()
    ies = seed_asset(assets)
    fixture = await service.create_fixture(fixture_payload(ies.id))
    await service.create_variant(fixture.id, variant_payload())
    with pytest.raises(HTTPException) as exc:
        await service.create_variant(fixture.id, variant_payload())
    assert exc.value.status_code == 409


async def test_get_variant_includes_fixture():
    service, assets, _, _, _ = make_service()
    ies = seed_asset(assets, "lamp.ies")
    fixture = await service.create_fixture(fixture_payload(ies.id))
    variant = await service.create_variant(fixture.id, variant_payload())
    detail = await service.get_variant(fixture.id, variant.id)
    assert detail.fixture.id == fixture.id
    assert detail.fixture.name == "High Bay"
    assert detail.fixture.ies_file.original_filename == "lamp.ies"
    assert not hasattr(detail.fixture, "variants")


async def test_parent_mismatch_404():
    service, assets, _, _, _ = make_service()
    ies = seed_asset(assets)
    a = await service.create_fixture(fixture_payload(ies.id, name="A"))
    b = await service.create_fixture(fixture_payload(ies.id, name="B"))
    variant = await service.create_variant(a.id, variant_payload())
    with pytest.raises(HTTPException) as exc:
        await service.get_variant(b.id, variant.id)
    assert exc.value.status_code == 404


async def test_patch_and_delete_fixture():
    service, assets, fixtures, _, _ = make_service()
    ies = seed_asset(assets)
    created = await service.create_fixture(fixture_payload(ies.id))
    with pytest.raises(HTTPException) as exc:
        await service.update_fixture(created.id, UpdateFixtureRequest())
    assert exc.value.status_code == 400
    updated = await service.update_fixture(created.id, UpdateFixtureRequest(name="Renamed"))
    assert updated.name == "Renamed"
    await service.delete_fixture(created.id)
    assert created.id not in fixtures.store.fixtures


async def test_duplicate_image_409():
    service, assets, _, _, _ = make_service()
    ies = seed_asset(assets)
    pic = seed_asset(assets, "a.png")
    fixture = await service.create_fixture(fixture_payload(ies.id))
    variant = await service.create_variant(fixture.id, variant_payload())
    await service.create_variant_image(fixture.id, variant.id, CreateVariantImageRequest(image_file_id=pic.id))
    with pytest.raises(HTTPException) as exc:
        await service.create_variant_image(fixture.id, variant.id, CreateVariantImageRequest(image_file_id=pic.id))
    assert exc.value.status_code == 409


async def test_patch_variant_and_delete_image():
    service, assets, _, variants, images = make_service()
    ies = seed_asset(assets)
    pic = seed_asset(assets, "a.png")
    fixture = await service.create_fixture(fixture_payload(ies.id))
    variant = await service.create_variant(fixture.id, variant_payload())
    attached = await service.create_variant_image(
        fixture.id, variant.id, CreateVariantImageRequest(image_file_id=pic.id)
    )
    patched = await service.update_variant(fixture.id, variant.id, UpdateVariantRequest(power=40))
    assert patched.power == 40
    await service.delete_variant_image(fixture.id, variant.id, attached.id)
    assert attached.id not in images.store.images
    await service.delete_variant(fixture.id, variant.id)
    assert variant.id not in variants.store.variants
