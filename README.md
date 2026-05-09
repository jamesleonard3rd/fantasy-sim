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

## Background Simulation

The `rts_world.sim` package implements the staggered region scheduler
described in `roadmap.txt`. The contract:

- The unit of work is a **region**. One tick = one wide `SELECT` (load) →
  pure-Python systems → one bulk `UPDATE`/`INSERT` (write), all in a single
  `BEGIN`/`COMMIT`.
- Only `sim/regions.py`, `sim/clock.py`, and `sim/events.py` touch Postgres.
  Everything under `sim/systems/` is pure Python over `RegionState`.
- `regions.paused = TRUE` means Unreal owns that region; the scheduler skips
  it until the flag clears.

Common workflows (a launcher script lives at `backend/scripts/sim.py`):

```bash
# Show all regions + the world clock.
python backend/scripts/sim.py status

# Create demo regions and round-robin existing entities into them.
python backend/scripts/sim.py seed-regions

# Tick one region once (handy for debugging a single system).
python backend/scripts/sim.py once --region-id 1

# Run the scheduler loop until SIGINT. Each region ticks every
# `tick_interval_seconds` (180s by default).
python backend/scripts/sim.py forever
```

Adding a new behaviour is "drop a file under `sim/systems/`, register it in
`systems/__init__.py:default_systems()`". Systems get `(state, ctx)` and
return a list of `PendingEvent` rows; they never touch the DB directly.

---

## Tests

Integration tests under `tests/` exercise the sim against the real local
database. They skip cleanly if Postgres is unreachable, so they are safe to
run anywhere.

```bash
pip install -r requirements-dev.txt
pytest -v
```

---

## Next Steps

1. First real system: opinion drift in `sim/systems/relationships.py`
   (roadmap §9.1). Validates the bulk UPDATE path and event emission.
2. Backfill `entity_zones.region_id` from the legacy `zone` text and start
   populating it on entity creation.
3. Once Unreal exists, document the paused-flag handoff and the
   `world_events` consumer contract in a separate doc.
