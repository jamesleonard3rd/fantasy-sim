export type Summary = {
  entities: number;
  factions: number;
  schools: number;
  items: number;
  abilities: number;
  traits: number;
  races: number;
  subraces: number;
  relationships: number;
};

export type EntitySummary = {
  id: number;
  name: string;
  type: string;
  race: string | null;
  subrace: string | null;
  zone: string | null;
  created_at: string;
};

export type EntityTrait = { id: number; name: string; description: string | null };
export type EntityFactionMembership = {
  id: number;
  name: string;
  rank: string;
  reputation: number;
};
export type EntityItem = {
  id: number;
  name: string;
  category: string | null;
  description: string | null;
  quantity: number;
};
export type EntityAbility = {
  id: number;
  name: string;
  description: string | null;
  type: string;
  cooldown_seconds: number;
  cost: number;
  damage: number;
  level: number;
  last_used_at: string | null;
};
export type EntitySchool = {
  school_id: number;
  school_name: string;
  status: string;
  enrolled_at: string;
};
export type EntityZone = { zone: string; updated_at: string } | null;
export type EntityPosition = {
  x: number;
  y: number;
  z: number;
  updated_at: string;
} | null;
export type EntityRelationship = {
  entity_id: number;
  entity_name: string;
  opinion: number;
  last_updated: string;
};

export type EntityDetail = EntitySummary & {
  traits: EntityTrait[];
  factions: EntityFactionMembership[];
  items: EntityItem[];
  abilities: EntityAbility[];
  schools: EntitySchool[];
  zone: EntityZone;
  position: EntityPosition;
  relationships: EntityRelationship[];
};

export type FactionSummary = {
  id: number;
  name: string;
  description: string | null;
  parent_id: number | null;
  parent_name: string | null;
  member_count: number;
  child_count: number;
  is_school: boolean;
};

export type FactionMember = {
  id: number;
  name: string;
  rank: string;
  reputation: number;
};

export type FactionChild = { id: number; name: string };

export type FactionSchoolBrief = {
  prestige: number;
  capacity: number | null;
  current_enrollment: number;
  min_enrollment_age: number | null;
  max_enrollment_age: number | null;
  enrollment_length: number | null;
  term_start_doy: number;
  term_end_doy: number;
  application_deadline_doy: number;
  entry_requirements: unknown;
} | null;

export type FactionDetail = FactionSummary & {
  children: FactionChild[];
  members: FactionMember[];
  school: FactionSchoolBrief;
};

export type SchoolSummary = {
  id: number;
  name: string;
  prestige: number;
  capacity: number | null;
  current_enrollment: number;
  min_enrollment_age: number | null;
  max_enrollment_age: number | null;
  enrollment_length: number | null;
  term_start_doy: number;
  term_end_doy: number;
  application_deadline_doy: number;
};

export type SchoolRosterEntry = {
  entity_id: number;
  name: string;
  status: string;
  enrolled_at: string;
};

export type SchoolDetail = SchoolSummary & {
  description: string | null;
  entry_requirements: unknown;
  roster: SchoolRosterEntry[];
};

export type Item = {
  id: number;
  name: string;
  description: string | null;
  category: string | null;
  total_owned: number;
};

export type Ability = {
  id: number;
  name: string;
  description: string | null;
  type: string;
  cooldown_seconds: number;
  cost: number;
  damage: number;
  holders: number;
};

export type Trait = {
  id: number;
  name: string;
  description: string | null;
  holders: number;
  modifiers: { stat: string; type: "add" | "mult"; value: number }[];
  grants_abilities: { id: number; name: string }[];
};

export type Race = {
  id: number;
  name: string;
  entity_count: number;
  subraces: { id: number; name: string }[];
};
