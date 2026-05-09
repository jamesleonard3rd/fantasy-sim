# RTS World Simulation – Database + Backend

This project is a backend system for a large-scale RTS / fantasy world simulation where hundreds to thousands of persistent NPCs exist at once. Each entity can have traits, factions, relationships, items, positions, and more. The world is backed by PostgreSQL using an ECS-style schema, and Python (`psycopg`) handles database access and simulation logic.

## Project Contents

- PostgreSQL schema (`schema.sql`)
- Python backend for connecting to PostgreSQL and running world logic
- Tools for loading the schema and extending gameplay systems
- Designed to work with Cursor/Codex for automated scaffolding and expansion

---

## Tech Stack

### Database

- PostgreSQL (via Postgres.app or local installation)
- Fully normalized schema
- Foreign keys, cascade behavior, and constraints

### Backend

- Python 3.12+
- psycopg for DB access
- dotenv for environment configuration

### Editor / Workflow

- VS Code + Cursor
- SQLTools / PostgreSQL extension for formatting and autocomplete

---

## Schema Overview

The database uses an ECS-style design.

### Core Tables

- **entities** – each NPC, creature, or object
  - includes name, kind, race, optional subrace
- **traits** – e.g. Brave, Clever, Strategic
- **factions** – guilds, kingdoms, organizations
- **items** – weapons, armor, potions, misc items

### Component Tables

- **entity_positions** – x/y/z for entity placement (loaded only when player views a region)
- **entity_zones** – which region/zone an entity belongs to (always loaded)
- **entity_factions** – many-to-many entity → faction with reputation
- **entity_traits** – many-to-many entity → traits
- **entity_items** – inventory quantities
- **entity_abilities** – per-entity ability levels and cooldowns
- **entity_schools** – student / graduate / instructor enrollment
- **relationships** – opinion score from -100 to 100

### Simulation Tables

- **regions** – top-level partitions the background sim ticks; each has its own
  `tick_interval_seconds` and `paused` flag (set true while Unreal owns the region)
- **world_events** – append-only log of actions the background sim took; the
  Unreal client reads new rows on region entry to summarize what happened
- **world_clock** – single-row table holding shared game time

This structure makes it easy to attach any component (traits, factions, etc.) to any entity.

---

## World Simulation Goals

The backend is designed to support:

- Persistent NPCs acting independently
- Area-based map partitioning
- Faction politics and alliances
- Trait-driven behavior
- NPC relationships with opinion values
- City and settlement simulation
- Territory control
- Jobs, goals, personality systems
- Dynamic world events
- Future AI expansions for decision-making

---

## Setup Instructions

### 1. Install Dependencies

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
# or, with dev tooling (mypy, pytest):
pip install -r requirements-dev.txt
```

Configure DB credentials in a `.env` file at the repo root (see `DB_HOST`,
`DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, or a single `DATABASE_URL`).

---

## Usage (backend lives in `backend/`)

- Initialize database (schema + seeds): `python backend/scripts/init_db.py`
- Schema only: `python backend/scripts/init_db.py --skip-seed`
- Connectivity ping: `python backend/main.py ping`
- Print sample generated entities: `python backend/scripts/demo_generate.py`
- Run the API: `uvicorn rts_world.api.main:app --reload --app-dir backend/src`

---

## Next Steps

1. Build the `rts_world.sim` package: a `regions` repository (load region working
   set, batched write-back), a `tick.tick_region(region_id)` orchestrator, and a
   heap-based `scheduler` that pops the next due region.
2. Add a CLI entry point `python -m rts_world.sim.runner` (and `--once` for tests).
3. Add the first concrete system under `sim/systems/` (e.g. opinion drift) and an
   end-to-end test that ticks one region against a temporary database.
4. Backfill `entity_zones.region_id` from the legacy `zone` text and start
   populating it on entity creation.
