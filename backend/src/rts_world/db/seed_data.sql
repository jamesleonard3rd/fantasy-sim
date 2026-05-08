-- Core lookups
INSERT INTO races (name) VALUES
    ('Human'),
    ('High Elf'),
    ('Dwarf'),
    ('Asteri'), -- Star touched humans born under rare celestial events.
    ('Greenskin')
ON CONFLICT (name) DO NOTHING;

INSERT INTO subraces (name, race_id) VALUES
    ('Varenic', (SELECT id FROM races WHERE name = 'Human')), --A river-valley people with a long history of trade and agriculture. 
    -- Warm-toned skin, dark hair, strong family clans.
    ('Varenic', (SELECT id FROM races WHERE name = 'Human')), -- Caldari
    --Lean builds, scarfed faces, nomadic ancestry.
    ('Rhovani', (SELECT id FROM races WHERE name = 'Human')), -- Steppe-riding horsefolk with nomadic traditions.
    ('Aurelian', (SELECT id FROM races WHERE name = 'Elf')), -- High elf
    ('Vaelori', (SELECT id FROM races WHERE name = 'Elf')), -- Wood elf
    ('Vel''Karim', (SELECT id FROM races WHERE name = 'Elf')) -- Dark elf

ON CONFLICT DO NOTHING;

INSERT INTO traits (name, description) VALUES
    ('Brave', 'Willing to take risks in combat'),
    ('Strong', 'Physically powerful'),
    ('Quick', 'Fast reflexes and movement'),
    ('Fast Learner', 'Gains skills more rapidly'),
    ('Tough', '{name} does not go down easily.'),
    ('Clever', '{name} picks up ideas quickly.'),
    ('Charming', '{name} has a way with people.'),
    ('Blood of the First King (Stirring)', 'The ancient blood is present, quiet but undeniable.'),
    ('Blood of the First King (Awakened)', 'The legacy begins to assert itself.'),
    ('Blood of the First King (Ascendant)', 'The First King’s legacy stands fully realized.'),
    ('Echo of Radiance', 'The light seems to favor {name}.'),
    ('Valemont Blood', ''),
    ('Natural Leader', ''),
    ('Beacon of Glory', ''),
    ('Arcane Lineage', ''),
    ('Flame Within', '')
ON CONFLICT (name) DO NOTHING;

INSERT INTO factions (name, description, parent_id) VALUES
    ('The White Tower', 'Mage tower of ', NULL),
    ('The Ember Court', 'Ruling nobility', NULL),
    ('The Flame Keepers', 'Elite knights of the Ember Court',
        (SELECT id FROM factions WHERE name = 'The Ember Court')
    ),
    ('The Red Tower', 'Mage tower of the Ember Court',
        (SELECT id FROM factions WHERE name = 'The Ember Court')
    ),
    ('Ember Academy', 'Prestigious academy for nobles and the wealthy at the Ember Court, specializing in fire magic.', 
        (SELECT id FROM factions WHERE name = 'The Ember Court')
    ),
    ('Celestria University', 'Most prestigious university for mages on the continent.', NULL)
ON CONFLICT (name) DO NOTHING;

INSERT INTO items (name, description, category) VALUES
    ('Iron Sword', 'Reliable steel blade', 'weapon'),
    ('Traveler''s Cloak', 'Keeps you warm and hidden', 'armor'),
    ('Healing Potion', 'Restores minor wounds', 'consumable')
ON CONFLICT (name) DO NOTHING;

INSERT INTO abilities (name, description, type, cooldown_seconds, cost, damage) VALUES
    ('Power Strike', 'Heavy melee attack', 'active', 8, 10, 25),
    ('Arcane Insight', 'Passive spell focus boost', 'passive', 0, 0, 0)
ON CONFLICT (name) DO NOTHING;









