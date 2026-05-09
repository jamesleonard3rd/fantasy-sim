CREATE TABLE IF NOT EXISTS races (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS subraces (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    race_id INT REFERENCES races(id) ON DELETE CASCADE,
    UNIQUE (race_id, name)
);

CREATE TABLE IF NOT EXISTS entities (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT DEFAULT 'humanoid' NOT NULL,
    race_id INT NOT NULL REFERENCES races(id),
    subrace_id INT REFERENCES subraces(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS traits (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS stats (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS trait_stat_modifiers (
    trait_id INT NOT NULL REFERENCES traits(id) ON DELETE CASCADE,
    stat_id INT NOT NULL REFERENCES stats(id) ON DELETE CASCADE,
    modifier_type TEXT NOT NULL CHECK (modifier_type IN ('add', 'mult')),
    value NUMERIC NOT NULL,
    PRIMARY KEY (trait_id, stat_id, modifier_type)
);

CREATE TABLE IF NOT EXISTS entity_traits (
    entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    trait_id INT NOT NULL REFERENCES traits(id) ON DELETE CASCADE,
    PRIMARY KEY (entity_id, trait_id)
);

CREATE TABLE IF NOT EXISTS factions (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT, 
    parent_id   INT REFERENCES factions(id) ON DELETE SET NULL
);

-- Discriminator for what flavor of organization this faction is. Houses,
-- knight orders, merchant guilds, schools, cults, etc. all live in factions
-- with a 1:1 detail table (e.g. houses, schools) hanging off them when they
-- need extra columns. 'generic' is the default for plain political factions.
ALTER TABLE factions
    ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'generic';
ALTER TABLE factions
    DROP CONSTRAINT IF EXISTS factions_kind_check;
ALTER TABLE factions
    ADD CONSTRAINT factions_kind_check
    CHECK (kind IN ('generic','house','order','guild','school','cult','company'));

CREATE TABLE IF NOT EXISTS entity_factions (
    entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    faction_id INT NOT NULL REFERENCES factions(id) ON DELETE CASCADE,
    rank TEXT NOT NULL CHECK (rank IN ('member', 'officer', 'leader', 'ally')),
    reputation SMALLINT DEFAULT 0 CHECK (reputation BETWEEN -100 AND 100),
    PRIMARY KEY (entity_id, faction_id)
);

-- Houses are factions (`factions.kind = 'house'`) with extra lineage rules.
-- Mirrors the schools-as-faction-detail pattern: name + description + parent
-- live in factions; everything below is house-specific.
--
-- The previous standalone houses + entity_houses tables (with their own id
-- and a many-to-many link) are dropped here so re-applying schema.sql
-- migrates a fresh-ish DB cleanly. There is no production data to preserve.
DROP TABLE IF EXISTS entity_houses;
DROP TABLE IF EXISTS houses;

CREATE TABLE IF NOT EXISTS houses (
    faction_id INT PRIMARY KEY REFERENCES factions(id) ON DELETE CASCADE,
    -- Sub-classification within the kind='house' factions: 'noble',
    -- 'merchant', 'royal', etc. Distinct from `factions.kind`, which says
    -- "this faction is a house"; this says "what flavor of house".
    type TEXT,
    default_surname TEXT,
    spawn_min INT,
    forced_traits JSONB,
    forced_magic JSONB,
    house_trait_counts JSONB,
    house_trait_weights JSONB,
    normal_trait_weight_mults JSONB,
    magic_type_counts JSONB,
    magic_weights JSONB
);

-- House membership: each entity belongs to at most ONE house. The PRIMARY
-- KEY on entity_id is what enforces that — the database literally cannot
-- store two house rows for the same entity. Other organizations (orders,
-- guilds, etc.) go through entity_factions and stack freely on top of this.
CREATE TABLE IF NOT EXISTS entity_houses (
    entity_id INT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    house_id INT NOT NULL REFERENCES houses(faction_id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    joined_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- Regions: top-level partition the world simulation iterates over.
-- Each region ticks independently on `tick_interval_seconds` cadence.
-- `paused` is set to true while Unreal is the live authority on this region.
CREATE TABLE IF NOT EXISTS regions (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    kind TEXT NOT NULL DEFAULT 'wilderness',
    tick_interval_seconds INT NOT NULL DEFAULT 180 CHECK (tick_interval_seconds > 0),
    last_tick_at TIMESTAMP WITH TIME ZONE,
    paused BOOLEAN NOT NULL DEFAULT FALSE
);

-- Zone: always loaded for world simulation. `zone` is a free-text label kept
-- for backwards compatibility; new code should populate `region_id`.
CREATE TABLE IF NOT EXISTS entity_zones (
    entity_id INT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    zone TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);
ALTER TABLE entity_zones
    ADD COLUMN IF NOT EXISTS region_id INT REFERENCES regions(id) ON DELETE SET NULL;

-- Position: only loaded when player views that zone
CREATE TABLE IF NOT EXISTS entity_positions (
    entity_id INT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    x INT NOT NULL,
    y INT NOT NULL,
    z INT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    category TEXT
);

CREATE TABLE IF NOT EXISTS entity_items (
    entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    item_id INT NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    quantity INT DEFAULT 1 NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (entity_id, item_id)
);

CREATE TABLE IF NOT EXISTS abilities (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    type TEXT NOT NULL CHECK (type IN ('active', 'passive')),
    cooldown_seconds INT DEFAULT 0 CHECK (cooldown_seconds >= 0),
    cost INT DEFAULT 0 CHECK (cost >= 0),
    damage INT DEFAULT 0 CHECK (damage >= 0)
);

CREATE TABLE IF NOT EXISTS trait_abilities (
    trait_id INT NOT NULL REFERENCES traits(id) ON DELETE CASCADE,
    ability_id INT NOT NULL REFERENCES abilities(id) ON DELETE CASCADE,
    PRIMARY KEY (trait_id, ability_id)
);

CREATE TABLE IF NOT EXISTS entity_abilities (
    entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    ability_id INT NOT NULL REFERENCES abilities(id) ON DELETE CASCADE,
    level INT DEFAULT 1 CHECK (level >= 1),
    last_used_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (entity_id, ability_id)
);

CREATE TABLE IF NOT EXISTS schools (
    faction_id  INT PRIMARY KEY REFERENCES factions(id) ON DELETE CASCADE,
    prestige INT NOT NULL,
    capacity INT, 
    current_enrollment INT NOT NULL DEFAULT 0, 
    min_enrollment_age INT,
    max_enrollment_age INT,
    enrollment_length INT, --years

    term_start_doy   INT NOT NULL, -- doy = day of year
    term_end_doy INT NOT NULL,
    application_deadline_doy INT NOT NULL,

    entry_requirements JSONB
);

CREATE TABLE IF NOT EXISTS entity_schools (
    entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    school_id INT NOT NULL REFERENCES schools(faction_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('student', 'graduate', 'instructor')),
    enrolled_at DATE DEFAULT CURRENT_DATE NOT NULL,
    PRIMARY KEY (entity_id, school_id)
);

CREATE TABLE IF NOT EXISTS relationships (
    subject_entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    opinion INT NOT NULL CHECK (opinion BETWEEN -100 AND 100),
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    PRIMARY KEY (subject_entity_id, target_entity_id),
    CHECK (subject_entity_id <> target_entity_id)
);

-- World events: append-only log of things the background sim did.
-- Unreal pulls events for a region since the player's last_seen timestamp on
-- region entry to summarize / replay what happened while away.
CREATE TABLE IF NOT EXISTS world_events (
    id BIGSERIAL PRIMARY KEY,
    region_id INT REFERENCES regions(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    subject_entity_id INT REFERENCES entities(id) ON DELETE SET NULL,
    target_entity_id INT REFERENCES entities(id) ON DELETE SET NULL,
    payload JSONB,
    occurred_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- World clock: single-row table holding global game time. Advanced by the
-- scheduler each tick so all systems agree on "now" without consulting the
-- wall clock independently.
CREATE TABLE IF NOT EXISTS world_clock (
    id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    game_day INT NOT NULL DEFAULT 0,
    game_tick BIGINT NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
INSERT INTO world_clock (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_entity_zones_zone ON entity_zones(zone);
CREATE INDEX IF NOT EXISTS idx_entity_zones_region ON entity_zones(region_id);
CREATE INDEX IF NOT EXISTS idx_entity_factions_faction ON entity_factions(faction_id);
CREATE INDEX IF NOT EXISTS idx_entity_traits_trait ON entity_traits(trait_id);
CREATE INDEX IF NOT EXISTS idx_entity_houses_house ON entity_houses(house_id);
CREATE INDEX IF NOT EXISTS idx_factions_kind ON factions(kind);
CREATE INDEX IF NOT EXISTS idx_relationships_subject ON relationships(subject_entity_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_entity_id);
CREATE INDEX IF NOT EXISTS idx_world_events_region_time
    ON world_events(region_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_regions_due
    ON regions(last_tick_at NULLS FIRST) WHERE paused = FALSE;
