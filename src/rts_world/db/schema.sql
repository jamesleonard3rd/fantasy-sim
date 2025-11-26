CREATE TABLE IF NOT EXISTS races (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS subraces (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS entities (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    race_id INT NOT NULL REFERENCES races(id),
    subrace_id INT REFERENCES subraces(id)
);

CREATE TABLE IF NOT EXISTS factions (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS positions (
    entity_id INT PRIMARY KEY REFERENCES entities(id) ON DELETE CASCADE,
    x INT NOT NULL,
    y INT NOT NULL,
    z INT NOT NULL,
    zone TEXT
);