export type SectionId =
  | "dashboard"
  | "entities"
  | "factions"
  | "schools"
  | "items"
  | "abilities"
  | "traits"
  | "races"
  | "towns";

export type GroupId = "overview" | "characters" | "catalog" | "world";

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
];

export const SECTIONS: Section[] = [
  { id: "dashboard", label: "Throne Room", group: "overview", status: "live" },

  { id: "entities", label: "Entities", group: "characters", status: "live" },
  { id: "factions", label: "Factions", group: "characters", status: "live" },
  { id: "schools", label: "Schools", group: "characters", status: "live" },

  { id: "items", label: "Items", group: "catalog", status: "live" },
  { id: "abilities", label: "Abilities", group: "catalog", status: "live" },
  { id: "traits", label: "Traits", group: "catalog", status: "live" },
  { id: "races", label: "Races", group: "catalog", status: "live" },

  { id: "towns", label: "Towns", group: "world", status: "planned" },
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
