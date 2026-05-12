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
  houses: number;
};

export type EntitySummary = {
  id: number;
  name: string;
  type: string;
  race: string | null;
  subrace: string | null;
  zone: string | null;
  house_id: number | null;
  house_name: string | null;
  house_role: string | null;
  created_at: string;
};

export type EntityTrait = { id: number; name: string; description: string | null };
export type EntityFactionMembership = {
  id: number;
  name: string;
  kind: FactionKind;
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
export type EntityZone = {
  zone: string;
  region_id: number | null;
  region_name: string | null;
  updated_at: string;
} | null;
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

export type EntityHouseMembership = {
  id: number;
  name: string;
  notes: string | null;
  type: string | null;
  default_surname: string | null;
  role: string;
  joined_at: string;
};

export type EntityDetail = EntitySummary & {
  traits: EntityTrait[];
  factions: EntityFactionMembership[];
  items: EntityItem[];
  abilities: EntityAbility[];
  zone: EntityZone;
  position: EntityPosition;
  relationships: EntityRelationship[];
  houses: EntityHouseMembership[];
  house: EntityHouseMembership | null;
};

export type FactionKind =
  | "generic"
  | "house"
  | "order"
  | "guild"
  | "school"
  | "cult"
  | "company";

export type FactionSummary = {
  id: number;
  name: string;
  description: string | null;
  kind: FactionKind;
  parent_id: number | null;
  parent_name: string | null;
  member_count: number;
  child_count: number;
  is_house: boolean;
};

export type FactionMember = {
  id: number;
  name: string;
  rank: string;
  reputation: number | null;
  source: "faction" | "house";
};

export type FactionChild = { id: number; name: string; kind: FactionKind };

export type FactionHouseBrief = {
  default_surname: string | null;
  spawn_min: number | null;
  forced_traits: string[] | null;
  forced_magic: string[] | null;
  house_trait_counts: Record<string, number> | null;
  house_trait_weights: Record<string, number> | null;
  normal_trait_weight_mults: Record<string, number> | null;
  magic_type_counts: Record<string, number> | null;
  magic_weights: Record<string, number> | null;
} | null;

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

export type FactionDetail = Omit<
  FactionSummary,
  "member_count" | "child_count" | "is_house"
> & {
  children: FactionChild[];
  members: FactionMember[];
  school: FactionSchoolBrief;
  house: FactionHouseBrief;
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
  rank: string;
  reputation: number;
};

export type SchoolDetail = SchoolSummary & {
  description: string | null;
  entry_requirements: unknown;
  roster: SchoolRosterEntry[];
};

export type RegionSummary = {
  id: number;
  name: string;
  type: string;
  parent_id: number | null;
  parent_name: string | null;
  tick_interval_seconds: number;
  paused: boolean;
  last_tick_at: string | null;
  direct_entity_count: number;
  entity_count: number;
  total_entity_count: number;
  child_count: number;
};

export type RegionResident = {
  id: number;
  name: string;
  zone: string;
  region_id: number;
  region_name: string;
  region_type: string;
};

export type RegionDetail = RegionSummary & {
  children: { id: number; name: string; type: string }[];
  residents: RegionResident[];
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

export type HouseSummary = {
  id: number;
  name: string;
  type: string | null;
  default_surname: string | null;
  notes: string | null;
  spawn_min: number | null;
  member_count: number;
};

export type HouseMember = {
  id: number;
  name: string;
  role: string;
  joined_at: string;
  race: string | null;
  subrace: string | null;
};

export type HouseAffiliatedFaction = {
  id: number;
  name: string;
  kind: FactionKind;
  member_count: number;
};

export type HouseDetail = HouseSummary & {
  forced_traits: string[] | null;
  forced_magic: string[] | null;
  house_trait_counts: Record<string, number> | null;
  house_trait_weights: Record<string, number> | null;
  normal_trait_weight_mults: Record<string, number> | null;
  magic_type_counts: Record<string, number> | null;
  magic_weights: Record<string, number> | null;
  members: HouseMember[];
  affiliated_factions: HouseAffiliatedFaction[];
};

export type SimStatus = {
  running: boolean;
  tick_count: number;
  min_interval_seconds: number;
  max_interval_seconds: number;
  next_tick_at: string | null;
  last_tick_at: string | null;
  last_region_id: number | null;
  last_region_name: string | null;
  last_game_day: number | null;
  last_game_tick: number | null;
  last_events_emitted: number;
  last_error: string | null;
};

export type SimEvent = {
  id: number;
  kind: string;
  significance: number;
  payload: Record<string, unknown> | null;
  occurred_at: string;
  region_name: string | null;
  subject_name: string | null;
  target_name: string | null;
  message: string;
};

export type SimClock = {
  running: boolean;
  game_day: number;
  hour: number;
  minute: number;
  minute_of_day: number;
  real_seconds_per_game_day: number;
};
