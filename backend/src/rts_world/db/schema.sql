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

CREATE TABLE IF NOT EXISTS entity_factions (
    entity_id INT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    faction_id INT NOT NULL REFERENCES factions(id) ON DELETE CASCADE,
    rank TEXT NOT NULL CHECK (rank IN ('member', 'officer', 'leader', 'ally')),
    reputation SMALLINT DEFAULT 0 CHECK (reputation BETWEEN -100 AND 100),
    PRIMARY KEY (entity_id, faction_id)
);

-- Zone: always loaded for world simulation
CREATE TABLE IF NOT EXISTS entity_zones (
    entity_id INT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    zone TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

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

CREATE INDEX IF NOT EXISTS idx_entity_zones_zone ON entity_zones(zone);
CREATE INDEX IF NOT EXISTS idx_entity_factions_faction ON entity_factions(faction_id);
CREATE INDEX IF NOT EXISTS idx_entity_traits_trait ON entity_traits(trait_id);
CREATE INDEX IF NOT EXISTS idx_relationships_subject ON relationships(subject_entity_id);
CREATE INDEX IF NOT EXISTS idx_relationships_target ON relationships(target_entity_id);
