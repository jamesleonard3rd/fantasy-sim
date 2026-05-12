export type SectionId =
  | "dashboard"
  | "entities"
  | "houses"
  | "factions"
  | "schools"
  | "regions"
  | "items"
  | "abilities"
  | "traits"
  | "races"
  | "towns"
  | "settings";

export type GroupId = "overview" | "characters" | "catalog" | "world" | "settings";

export type Section = {
  id: SectionId;
  label: string;
  group: GroupId;
  status: "live" | "planned";
};

export type Group = {
  id: GroupId;
  label: string;
};

export const GROUPS: Group[] = [
  { id: "overview", label: "Overview" },
  { id: "characters", label: "Court" },
  { id: "catalog", label: "Codex" },
  { id: "world", label: "Realm" },
  { id: "settings", label: "Settings" },
];

export const SECTIONS: Section[] = [
  { id: "dashboard", label: "Throne Room", group: "overview", status: "live" },

  { id: "entities", label: "Entities", group: "characters", status: "live" },
  { id: "houses", label: "Houses", group: "characters", status: "live" },
  { id: "factions", label: "Factions", group: "characters", status: "live" },
  { id: "schools", label: "Schools", group: "characters", status: "live" },

  { id: "items", label: "Items", group: "catalog", status: "live" },
  { id: "abilities", label: "Abilities", group: "catalog", status: "live" },
  { id: "traits", label: "Traits", group: "catalog", status: "live" },
  { id: "races", label: "Races", group: "catalog", status: "live" },

  { id: "regions", label: "Regions", group: "world", status: "live" },
  { id: "towns", label: "Towns", group: "world", status: "planned" },

  { id: "settings", label: "Game Settings", group: "settings", status: "live" },
];

export function sectionsForGroup(groupId: GroupId): Section[] {
  return SECTIONS.filter((s) => s.group === groupId);
}

export function firstSectionForGroup(groupId: GroupId): SectionId {
  const list = sectionsForGroup(groupId);
  return list[0]?.id ?? "dashboard";
}

export function groupForSection(id: SectionId): GroupId {
  return SECTIONS.find((s) => s.id === id)?.group ?? "overview";
}
