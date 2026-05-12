from __future__ import annotations

import ast
import os
import uuid
from pathlib import Path

import pytest

from rts_world.api.main import get_school
from rts_world.services import entities as entity_service


@pytest.fixture
def entity_mutation_fixture(db_conn):
    prefix = f"__test_entity_service_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    ids: dict[str, int] = {}

    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO races (name) VALUES (%s) RETURNING id", (f"{prefix}_race",))
        ids["race_id"] = int(cur.fetchone()[0])

        cur.execute(
            """
            INSERT INTO entities (name, race_id)
            VALUES (%s, %s)
            RETURNING id
            """,
            (f"{prefix}_entity", ids["race_id"]),
        )
        ids["entity_id"] = int(cur.fetchone()[0])

        cur.execute(
            """
            INSERT INTO regions (name, type, tick_interval_seconds)
            VALUES (%s, 'region', 180)
            RETURNING id
            """,
            (f"{prefix}_region",),
        )
        ids["region_id"] = int(cur.fetchone()[0])

        cur.execute(
            "INSERT INTO traits (name, description) VALUES (%s, %s) RETURNING id",
            (f"{prefix}_trait", "test trait"),
        )
        ids["trait_id"] = int(cur.fetchone()[0])

        cur.execute(
            """
            INSERT INTO factions (name, description, kind)
            VALUES (%s, %s, 'school')
            RETURNING id
            """,
            (f"{prefix}_faction", "test faction"),
        )
        ids["faction_id"] = int(cur.fetchone()[0])

        cur.execute(
            """
            INSERT INTO schools (
                faction_id, prestige, term_start_doy, term_end_doy,
                application_deadline_doy
            )
            VALUES (%s, 1, 1, 100, 300)
            """,
            (ids["faction_id"],),
        )

        cur.execute(
            """
            INSERT INTO items (name, description, category)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (f"{prefix}_item", "test item", "test"),
        )
        ids["item_id"] = int(cur.fetchone()[0])

        cur.execute(
            """
            INSERT INTO abilities (name, description, type)
            VALUES (%s, %s, 'active')
            RETURNING id
            """,
            (f"{prefix}_ability", "test ability"),
        )
        ids["ability_id"] = int(cur.fetchone()[0])

    db_conn.commit()

    try:
        yield ids
    finally:
        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM entities WHERE id = %s", (ids["entity_id"],))
            cur.execute("DELETE FROM schools WHERE faction_id = %s", (ids["faction_id"],))
            cur.execute("DELETE FROM factions WHERE id = %s", (ids["faction_id"],))
            cur.execute("DELETE FROM traits WHERE id = %s", (ids["trait_id"],))
            cur.execute("DELETE FROM items WHERE id = %s", (ids["item_id"],))
            cur.execute("DELETE FROM abilities WHERE id = %s", (ids["ability_id"],))
            cur.execute("DELETE FROM regions WHERE id = %s", (ids["region_id"],))
            cur.execute("DELETE FROM races WHERE id = %s", (ids["race_id"],))
        db_conn.commit()


def test_entity_service_mutates_components_and_reads_detail(
    db_conn,
    entity_mutation_fixture,
) -> None:
    ids = entity_mutation_fixture
    entity_id = ids["entity_id"]

    entity_service.set_entity_zone(db_conn, entity_id, ids["region_id"])
    entity_service.add_entity_trait(db_conn, entity_id, ids["trait_id"])
    entity_service.set_entity_faction(
        db_conn,
        entity_id,
        ids["faction_id"],
        "officer",
        25,
    )
    entity_service.add_entity_item(db_conn, entity_id, ids["item_id"], 2)
    entity_service.add_entity_item(db_conn, entity_id, ids["item_id"], 3)
    entity_service.set_entity_ability(db_conn, entity_id, ids["ability_id"], 4)

    detail = entity_service.get_entity_detail(db_conn, entity_id)

    assert detail is not None
    assert detail["zone"]["region_id"] == ids["region_id"]
    assert detail["zone"]["zone"].endswith("_region")
    assert [trait["id"] for trait in detail["traits"]] == [ids["trait_id"]]
    assert detail["factions"][0]["id"] == ids["faction_id"]
    assert detail["factions"][0]["kind"] == "school"
    assert detail["factions"][0]["rank"] == "officer"
    assert detail["factions"][0]["reputation"] == 25
    assert detail["items"][0]["id"] == ids["item_id"]
    assert detail["items"][0]["quantity"] == 5
    assert detail["abilities"][0]["id"] == ids["ability_id"]
    assert detail["abilities"][0]["level"] == 4

    db_conn.commit()
    school = get_school(ids["faction_id"])
    assert school["current_enrollment"] == 1
    assert school["roster"] == [
        {
            "entity_id": entity_id,
            "name": detail["name"],
            "rank": "officer",
            "reputation": 25,
        }
    ]

    entity_service.remove_entity_trait(db_conn, entity_id, ids["trait_id"])
    entity_service.remove_entity_faction(db_conn, entity_id, ids["faction_id"])
    entity_service.remove_entity_item(db_conn, entity_id, ids["item_id"])
    entity_service.remove_entity_ability(db_conn, entity_id, ids["ability_id"])

    detail = entity_service.get_entity_detail(db_conn, entity_id)

    assert detail is not None
    assert detail["traits"] == []
    assert detail["factions"] == []
    assert detail["items"] == []
    assert detail["abilities"] == []

    db_conn.commit()


def test_entity_service_raises_domain_errors(db_conn, entity_mutation_fixture) -> None:
    ids = entity_mutation_fixture

    with pytest.raises(entity_service.EntityNotFound):
        entity_service.add_entity_trait(db_conn, -12345, ids["trait_id"])

    with pytest.raises(entity_service.TraitNotFound):
        entity_service.add_entity_trait(db_conn, ids["entity_id"], -12345)

    with pytest.raises(entity_service.RegionNotFound):
        entity_service.set_entity_zone(db_conn, ids["entity_id"], -12345)


def test_sim_systems_do_not_import_services_or_repositories() -> None:
    systems_dir = (
        Path(__file__).resolve().parents[1]
        / "backend"
        / "src"
        / "rts_world"
        / "sim"
        / "systems"
    )
    forbidden_modules = {
        "rts_world.services",
        "rts_world.db",
        "services",
        "entity_repository",
    }

    for path in systems_dir.glob("*.py"):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue

            for module in modules:
                assert not any(
                    module == forbidden or module.startswith(f"{forbidden}.")
                    for forbidden in forbidden_modules
                ), f"{path.name} imports forbidden persistence module {module!r}"
