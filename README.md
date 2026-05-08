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

- **positions** – x/y/z + zone for entity placement
- **entity_factions** – many-to-many entity → faction with reputation
- (optional) **entity_traits** – many-to-many entity → traits
- (planned) **abilities** – active/passive abilities with cooldown, cost, damage
- (planned) **schools** – humanoid entities attending institutions
- (planned) **relationships** – opinion score from -100 to 100

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
python3 -m venv venv
source venv/bin/activate
pip install psycopg python-dotenv
```

---

## Usage (backend now lives in `backend/`)

- Initialize database (schema + seeds): `python backend/scripts/init_db.py`
- Schema only: `python backend/scripts/init_db.py --skip-seed`
- Connectivity check/sample run: `python backend/main.py`
- Integration smoke test (requires running Postgres): `python -m unittest tests/test_db_smoke.py`

---

## Next Steps

1. Expand `backend/src/rts_world/db/schema.sql` with planned components (traits/entity_traits, relationships with opinion score, abilities, schools, items) and fix the `positions` semicolon; align `backend/src/rts_world/db/seed_data.sql` to match.
2. Add constraints and indexes: `UNIQUE` on lookup names, cascades on join tables, check constraints (opinion range, rank enums), and spatial indexes for common position queries.
3. Create a helper (e.g., `backend/scripts/init_db.py`) to load schema + seed data using `psycopg` and `.env` connection settings; wire `backend/main.py` to use it.
4. Add a minimal migration/check pipeline (e.g., `make` or `tox`) to run schema load, seeds, and integrity checks automatically.
5. Write a small integration test that inserts a sample entity with traits/factions/position and verifies the relationships round-trip.
