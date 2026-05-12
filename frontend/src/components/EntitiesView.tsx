import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "../api";
import type {
  Ability,
  EntityDetail,
  EntitySummary,
  FactionSummary,
  Item,
  RegionSummary,
  Trait,
} from "../types";
import { MasterDetail } from "./MasterDetail";
import { ErrorBox, Field, Section, Tag, formatDate } from "./common";

function EntitiesView({ refreshKey }: { refreshKey: number }) {
  return (
    <MasterDetail<EntitySummary, EntityDetail>
      key={refreshKey}
      listEndpoint="/entities"
      detailEndpoint={(id) => `/entities/${id}`}
      getId={(e) => e.id}
      getTitle={(e) => e.name}
      getSubtitle={(e) => {
        const lineage = [e.race, e.subrace].filter(Boolean).join(" · ");
        if (e.house_name) {
          const role = e.house_role ? ` (${e.house_role})` : "";
          return `${e.house_name}${role}${lineage ? ` · ${lineage}` : ""}`;
        }
        return lineage || e.type;
      }}
      getMeta={(e) => `#${e.id}${e.zone ? ` · ${e.zone}` : ""}`}
      searchPlaceholder="Search entities by name, race, house, zone…"
      emptyMessage="No entities yet. Try seeding the database."
      renderDetail={(entity) => <EntityDetailPanel entity={entity} />}
    />
  );
}

type LookupData = {
  traits: Trait[];
  factions: FactionSummary[];
  items: Item[];
  abilities: Ability[];
  regions: RegionSummary[];
};

function EntityDetailPanel({ entity }: { entity: EntityDetail }) {
  const [current, setCurrent] = useState(entity);
  const [lookups, setLookups] = useState<LookupData | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [editingZone, setEditingZone] = useState(false);
  const [selectedTraitId, setSelectedTraitId] = useState("");
  const [selectedFactionId, setSelectedFactionId] = useState("");
  const [selectedSchoolId, setSelectedSchoolId] = useState("");
  const [selectedItemId, setSelectedItemId] = useState("");
  const [itemQuantity, setItemQuantity] = useState(1);
  const [selectedAbilityId, setSelectedAbilityId] = useState("");
  const [selectedRegionId, setSelectedRegionId] = useState("");

  useEffect(() => {
    setCurrent(entity);
    setEditingZone(false);
    setError("");
  }, [entity]);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      apiGet<Trait[]>("/traits"),
      apiGet<FactionSummary[]>("/factions"),
      apiGet<Item[]>("/items"),
      apiGet<Ability[]>("/abilities"),
      apiGet<RegionSummary[]>("/regions"),
    ])
      .then(([traits, factions, items, abilities, regions]) => {
        if (!cancelled) {
          setLookups({ traits, factions, items, abilities, regions });
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const availableTraits = useMemo(() => {
    const existing = new Set(current.traits.map((t) => t.id));
    return (lookups?.traits ?? []).filter((trait) => !existing.has(trait.id));
  }, [current.traits, lookups]);

  const availableFactions = useMemo(() => {
    const existing = new Set(current.factions.map((f) => f.id));
    return (lookups?.factions ?? []).filter(
      (faction) =>
        faction.kind !== "school" && !faction.is_house && !existing.has(faction.id),
    );
  }, [current.factions, lookups]);

  const visibleFactions = useMemo(
    () => current.factions.filter((faction) => faction.kind !== "school"),
    [current.factions],
  );

  const availableItems = useMemo(() => {
    const existing = new Set(current.items.map((item) => item.id));
    return (lookups?.items ?? []).filter((item) => !existing.has(item.id));
  }, [current.items, lookups]);

  const availableAbilities = useMemo(() => {
    const existing = new Set(current.abilities.map((ability) => ability.id));
    return (lookups?.abilities ?? []).filter((ability) => !existing.has(ability.id));
  }, [current.abilities, lookups]);

  const schoolFactions = useMemo(
    () => current.factions.filter((faction) => faction.kind === "school"),
    [current.factions],
  );

  const availableSchoolFactions = useMemo(() => {
    const existing = new Set(current.factions.map((f) => f.id));
    return (lookups?.factions ?? []).filter(
      (faction) => faction.kind === "school" && !existing.has(faction.id),
    );
  }, [current.factions, lookups]);

  const runEdit = async (operation: () => Promise<EntityDetail>) => {
    setBusy(true);
    setError("");
    try {
      setCurrent(await operation());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Entity edit failed.");
    } finally {
      setBusy(false);
    }
  };

  const addTrait = () => {
    const traitId = Number(selectedTraitId || availableTraits[0]?.id);
    if (!traitId) return;
    void runEdit(() => apiPost<EntityDetail>(`/entities/${current.id}/traits/${traitId}`));
    setSelectedTraitId("");
  };

  const addFaction = () => {
    const factionId = Number(selectedFactionId || availableFactions[0]?.id);
    if (!factionId) return;
    void runEdit(() =>
      apiPost<EntityDetail>(`/entities/${current.id}/factions/${factionId}`, {
        rank: "member",
        reputation: 0,
      }),
    );
    setSelectedFactionId("");
  };

  const addSchool = () => {
    const schoolId = Number(selectedSchoolId || availableSchoolFactions[0]?.id);
    if (!schoolId) return;
    void runEdit(() =>
      apiPost<EntityDetail>(`/entities/${current.id}/factions/${schoolId}`, {
        rank: "student",
        reputation: 0,
      }),
    );
    setSelectedSchoolId("");
  };

  const addItem = () => {
    const itemId = Number(selectedItemId || availableItems[0]?.id);
    if (!itemId) return;
    void runEdit(() =>
      apiPost<EntityDetail>(`/entities/${current.id}/items/${itemId}`, {
        quantity: Math.max(1, Math.floor(itemQuantity)),
      }),
    );
    setSelectedItemId("");
    setItemQuantity(1);
  };

  const addAbility = () => {
    const abilityId = Number(selectedAbilityId || availableAbilities[0]?.id);
    if (!abilityId) return;
    void runEdit(() =>
      apiPost<EntityDetail>(`/entities/${current.id}/abilities/${abilityId}`, {
        level: 1,
      }),
    );
    setSelectedAbilityId("");
  };

  const saveZone = () => {
    const fallbackRegionId = current.zone?.region_id ?? lookups?.regions[0]?.id;
    const regionId = Number(selectedRegionId || fallbackRegionId);
    if (!regionId) return;
    void runEdit(() =>
      apiPut<EntityDetail>(`/entities/${current.id}/zone`, { region_id: regionId }),
    );
    setEditingZone(false);
    setSelectedRegionId("");
  };

  return (
    <div className="detail">
      {error && <ErrorBox message={error} />}

      <div className="detail-header">
        <div>
          <h2>{current.name}</h2>
          <div className="detail-subtitle">
            {[current.race, current.subrace].filter(Boolean).join(" · ") ||
              current.type}
          </div>
        </div>
        <Tag tone="info">#{current.id}</Tag>
      </div>

      <div className="field-grid">
        <Field label="Type" value={current.type} />
        <Field label="Race" value={current.race ?? "—"} />
        <Field label="Subrace" value={current.subrace ?? "—"} />
        <Field
          label="House"
          value={
            current.house ? (
              <span>
                {current.house.name}{" "}
                <span className="muted small">({current.house.role})</span>
              </span>
            ) : (
              "—"
            )
          }
        />
        <Field
          label="Zone"
          value={
            editingZone ? (
              <span className="inline-edit-row">
                <select
                  value={selectedRegionId || String(current.zone?.region_id ?? "")}
                  onChange={(event) => setSelectedRegionId(event.target.value)}
                  disabled={busy || !lookups}
                >
                  {(lookups?.regions ?? []).map((region) => (
                    <option key={region.id} value={region.id}>
                      {region.name} ({region.type})
                    </option>
                  ))}
                </select>
                <button type="button" disabled={busy} onClick={saveZone}>
                  Save
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => setEditingZone(false)}
                >
                  Cancel
                </button>
              </span>
            ) : (
              <button
                type="button"
                className="inline-edit-value"
                title="Click to change location"
                onClick={() => {
                  setSelectedRegionId(String(current.zone?.region_id ?? ""));
                  setEditingZone(true);
                }}
              >
                {current.zone?.zone ?? "—"}
              </button>
            )
          }
        />
        <Field
          label="Position"
          value={
            current.position
              ? `(${current.position.x}, ${current.position.y}, ${current.position.z})`
              : "—"
          }
        />
        <Field label="Created" value={formatDate(current.created_at)} />
      </div>

      {current.houses.length > 0 && (
        <Section title={`Houses (${current.houses.length})`}>
          <table className="data-table">
            <thead>
              <tr>
                <th>House</th>
                <th>Role</th>
                <th>Type</th>
                <th>Joined</th>
              </tr>
            </thead>
            <tbody>
              {current.houses.map((h) => (
                <tr key={h.id}>
                  <td>{h.name}</td>
                  <td>
                    <Tag tone={houseRoleTone(h.role)}>{h.role}</Tag>
                  </td>
                  <td>{h.type ?? "—"}</td>
                  <td>{formatDate(h.joined_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}

      <Section
        title={`Traits (${current.traits.length})`}
        actions={
          <AddControl
            label="trait"
            value={selectedTraitId}
            onChange={setSelectedTraitId}
            options={availableTraits}
            disabled={busy || !lookups}
            onAdd={addTrait}
          />
        }
      >
        {current.traits.length === 0 ? (
          <span className="muted">No traits.</span>
        ) : (
          <div className="chip-row">
            {current.traits.map((t) => (
              <span className="editable-chip" key={t.id}>
                <Tag tone="info">{t.name}</Tag>
                <button
                  type="button"
                  disabled={busy}
                  aria-label={`Remove ${t.name}`}
                  onClick={() =>
                    void runEdit(() =>
                      apiDelete<EntityDetail>(`/entities/${current.id}/traits/${t.id}`),
                    )
                  }
                >
                  x
                </button>
              </span>
            ))}
          </div>
        )}
      </Section>

      <Section
        title={`Factions (${visibleFactions.length})`}
        actions={
          <AddControl
            label="faction"
            value={selectedFactionId}
            onChange={setSelectedFactionId}
            options={availableFactions}
            disabled={busy || !lookups}
            onAdd={addFaction}
          />
        }
      >
        {visibleFactions.length === 0 ? (
          <span className="muted">Not affiliated.</span>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Faction</th>
                <th>Rank</th>
                <th>Reputation</th>
                <th className="table-actions-heading" />
              </tr>
            </thead>
            <tbody>
              {visibleFactions.map((f) => (
                <tr key={f.id}>
                  <td>{f.name}</td>
                  <td>
                    <Tag tone="neutral">{f.rank}</Tag>
                  </td>
                  <td>{f.reputation}</td>
                  <td className="table-actions">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void runEdit(() =>
                          apiDelete<EntityDetail>(
                            `/entities/${current.id}/factions/${f.id}`,
                          ),
                        )
                      }
                    >
                      x
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section
        title={`Schools (${schoolFactions.length})`}
        actions={
          <AddControl
            label="school"
            value={selectedSchoolId}
            onChange={setSelectedSchoolId}
            options={availableSchoolFactions}
            disabled={busy || !lookups}
            onAdd={addSchool}
          />
        }
      >
        {schoolFactions.length === 0 ? (
          <span className="muted">No school faction memberships.</span>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>School</th>
                <th>Rank</th>
                <th>Reputation</th>
                <th className="table-actions-heading" />
              </tr>
            </thead>
            <tbody>
              {schoolFactions.map((f) => (
                <tr key={f.id}>
                  <td>{f.name}</td>
                  <td>
                    <Tag tone="info">{f.rank}</Tag>
                  </td>
                  <td>{f.reputation}</td>
                  <td className="table-actions">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void runEdit(() =>
                          apiDelete<EntityDetail>(
                            `/entities/${current.id}/factions/${f.id}`,
                          ),
                        )
                      }
                    >
                      x
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section
        title={`Inventory (${current.items.length})`}
        actions={
          <AddControl
            label="item"
            value={selectedItemId}
            onChange={setSelectedItemId}
            options={availableItems}
            disabled={busy || !lookups}
            onAdd={addItem}
            extra={
              <input
                className="add-control-qty"
                type="number"
                min={1}
                value={itemQuantity}
                onChange={(event) => setItemQuantity(Number(event.target.value) || 1)}
              />
            }
          />
        }
      >
        {current.items.length === 0 ? (
          <span className="muted">Empty inventory.</span>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Category</th>
                <th>Qty</th>
                <th className="table-actions-heading" />
              </tr>
            </thead>
            <tbody>
              {current.items.map((it) => (
                <tr key={it.id}>
                  <td>
                    <div>{it.name}</div>
                    {it.description && (
                      <div className="muted small">{it.description}</div>
                    )}
                  </td>
                  <td>{it.category ?? "—"}</td>
                  <td>{it.quantity}</td>
                  <td className="table-actions">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void runEdit(() =>
                          apiDelete<EntityDetail>(`/entities/${current.id}/items/${it.id}`),
                        )
                      }
                    >
                      x
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section
        title={`Abilities (${current.abilities.length})`}
        actions={
          <AddControl
            label="ability"
            value={selectedAbilityId}
            onChange={setSelectedAbilityId}
            options={availableAbilities}
            disabled={busy || !lookups}
            onAdd={addAbility}
          />
        }
      >
        {current.abilities.length === 0 ? (
          <span className="muted">No abilities learned.</span>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Ability</th>
                <th>Type</th>
                <th>Lvl</th>
                <th>Cost</th>
                <th>Damage</th>
                <th>Cooldown</th>
                <th>Last used</th>
                <th className="table-actions-heading" />
              </tr>
            </thead>
            <tbody>
              {current.abilities.map((a) => (
                <tr key={a.id}>
                  <td>{a.name}</td>
                  <td>
                    <Tag tone={a.type === "active" ? "warning" : "neutral"}>
                      {a.type}
                    </Tag>
                  </td>
                  <td>{a.level}</td>
                  <td>{a.cost}</td>
                  <td>{a.damage}</td>
                  <td>{a.cooldown_seconds}s</td>
                  <td>{formatDate(a.last_used_at)}</td>
                  <td className="table-actions">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() =>
                        void runEdit(() =>
                          apiDelete<EntityDetail>(
                            `/entities/${current.id}/abilities/${a.id}`,
                          ),
                        )
                      }
                    >
                      x
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title={`Relationships (${current.relationships.length})`}>
        {current.relationships.length === 0 ? (
          <span className="muted">No tracked relationships.</span>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Toward</th>
                <th>Opinion</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {current.relationships.map((r) => (
                <tr key={r.entity_id}>
                  <td>{r.entity_name}</td>
                  <td>
                    <Tag tone={opinionTone(r.opinion)}>{r.opinion}</Tag>
                  </td>
                  <td>{formatDate(r.last_updated)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  );
}

function AddControl({
  label,
  value,
  onChange,
  options,
  disabled,
  onAdd,
  extra,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { id: number; name: string }[];
  disabled: boolean;
  onAdd: () => void;
  extra?: ReactNode;
}) {
  return (
    <div className="add-control">
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled || options.length === 0}
      >
        <option value="">Add {label}...</option>
        {options.map((option) => (
          <option key={option.id} value={option.id}>
            {option.name}
          </option>
        ))}
      </select>
      {extra}
      <button
        type="button"
        disabled={disabled || options.length === 0}
        onClick={onAdd}
        title={`Add ${label}`}
      >
        +
      </button>
    </div>
  );
}

function opinionTone(value: number): "success" | "danger" | "neutral" {
  if (value > 20) return "success";
  if (value < -20) return "danger";
  return "neutral";
}

function houseRoleTone(role: string): "warning" | "info" | "success" | "neutral" {
  if (role === "patriarch" || role === "matriarch") return "warning";
  if (role === "heir") return "success";
  if (role === "scion") return "info";
  return "neutral";
}

export default EntitiesView;
