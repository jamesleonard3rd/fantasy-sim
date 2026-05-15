import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { apiDelete, apiGet, apiPost, apiPut } from "../api";
import type {
  Ability,
  EntityDetail,
  EntityGoal,
  EntitySummary,
  FactionSummary,
  GoalTemplateSummary,
  Item,
  RegionSummary,
  Trait,
} from "../types";
import { MasterDetail } from "./MasterDetail";
import { TravelRoutePreview } from "./TravelRoutePreview";
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
          const rank = e.house_rank ? ` (${e.house_rank})` : "";
          return `${e.house_name}${rank}${lineage ? ` · ${lineage}` : ""}`;
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
  goalTemplates: GoalTemplateSummary[];
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
  const [selectedGoalType, setSelectedGoalType] = useState("");
  const [goalPayloadJson, setGoalPayloadJson] = useState("{}");
  const [travelDestRegionId, setTravelDestRegionId] = useState("");

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
      apiGet<GoalTemplateSummary[]>("/goal-templates").catch(() => []),
    ])
      .then(([traits, factions, items, abilities, regions, goalTemplates]) => {
        if (!cancelled) {
          setLookups({ traits, factions, items, abilities, regions, goalTemplates });
        }
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (selectedGoalType !== "travel_to_region") {
      setTravelDestRegionId("");
    }
  }, [selectedGoalType]);

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
    () =>
      current.factions.filter(
        (faction) => faction.kind !== "school" && faction.kind !== "house",
      ),
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

  const goals = current.goals ?? [];

  const { rootGoals, goalsByParent } = useMemo(() => buildGoalHierarchy(goals), [goals]);

  const availableGoalTemplates = lookups?.goalTemplates ?? [];

  const selectedGoalTemplate = useMemo(
    () => availableGoalTemplates.find((x) => x.goal_type === selectedGoalType),
    [availableGoalTemplates, selectedGoalType],
  );

  const selectedGoalTemplateHint = useMemo(() => {
    if (selectedGoalType === "travel_to_region") {
      return 'Optional JSON for extras only, e.g. {"duration_ticks": 10} (use {} if not needed).';
    }
    if (!selectedGoalTemplate?.requires?.length) return undefined;
    return `Requires payload fields: ${selectedGoalTemplate.requires.join(", ")}`;
  }, [selectedGoalTemplate, selectedGoalType]);

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

  const addGoal = () => {
    if (!selectedGoalType || !selectedGoalTemplate || !lookups) {
      setError("Choose a goal template before adding a goal.");
      return;
    }
    const raw = goalPayloadJson.trim();
    let payload: Record<string, unknown> = {};
    if (raw) {
      try {
        const parsed: unknown = JSON.parse(raw);
        if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
          setError("Goal payload must be a JSON object.");
          return;
        }
        payload = parsed as Record<string, unknown>;
      } catch {
        setError("Goal payload must be valid JSON.");
        return;
      }
    }
    if (selectedGoalType === "travel_to_region") {
      const rid = Number(travelDestRegionId);
      if (!Number.isFinite(rid) || rid <= 0) {
        setError("Choose a destination region.");
        return;
      }
      payload = { ...payload, region_id: rid };
      delete payload.target_region_id;
    }
    const missing = selectedGoalTemplate.requires.filter(
      (field) => payload[field] === undefined || payload[field] === null,
    );
    if (missing.length > 0) {
      setError(`Goal payload is missing: ${missing.join(", ")}.`);
      return;
    }
    void runEdit(() =>
      apiPost<EntityDetail>(`/entities/${current.id}/goals`, {
        goal_type: selectedGoalType,
        payload,
        completion_mode: selectedGoalTemplate.completion_mode,
      }),
    );
    setSelectedGoalType("");
    setGoalPayloadJson("{}");
    setTravelDestRegionId("");
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
                <span className="muted small">({current.house.rank})</span>
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
                <th>Rank</th>
                <th>Type</th>
                <th>Joined</th>
              </tr>
            </thead>
            <tbody>
              {current.houses.map((h) => (
                <tr key={h.id}>
                  <td>{h.name}</td>
                  <td>
                    <Tag tone={houseRankTone(h.rank)}>{h.rank}</Tag>
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
        title={`Goals (${rootGoals.length})`}
        actions={
          <div className="add-control add-control-goals">
            <select
              value={selectedGoalType}
              onChange={(event) => setSelectedGoalType(event.target.value)}
              disabled={busy || !lookups || availableGoalTemplates.length === 0}
              title={selectedGoalTemplateHint}
            >
              <option value="">Add goal template…</option>
              {availableGoalTemplates.map((t) => (
                <option key={t.goal_type} value={t.goal_type}>
                  {formatGoalType(t.goal_type)}
                </option>
              ))}
            </select>
            {selectedGoalType === "travel_to_region" && lookups && (
              <select
                value={travelDestRegionId}
                onChange={(event) => setTravelDestRegionId(event.target.value)}
                disabled={busy || availableGoalTemplates.length === 0}
                title="Destination region"
              >
                <option value="">Destination region…</option>
                {[...lookups.regions]
                  .sort((a, b) => a.name.localeCompare(b.name))
                  .map((r) => (
                    <option key={r.id} value={String(r.id)}>
                      {r.name}
                    </option>
                  ))}
              </select>
            )}
            <textarea
              className="add-control-payload"
              rows={1}
              value={goalPayloadJson}
              onChange={(event) => setGoalPayloadJson(event.target.value)}
              disabled={busy || !lookups || availableGoalTemplates.length === 0}
              placeholder={
                selectedGoalType === "travel_to_region"
                  ? 'Optional: {"duration_ticks": 10}'
                  : 'Payload JSON, e.g. {"faction_id": 1, "target_region_id": 2}'
              }
              spellCheck={false}
            />
            <button
              type="button"
              disabled={
                busy || !lookups || availableGoalTemplates.length === 0 || !selectedGoalType
              }
              onClick={addGoal}
              title="Add goal from template"
            >
              +
            </button>
          </div>
        }
      >
        {availableGoalTemplates.length === 0 && lookups && (
          <p className="muted small">
            No goal templates loaded (is the API running?). You can still remove goals below.
          </p>
        )}
        {selectedGoalTemplateHint && (
          <p className="muted small">{selectedGoalTemplateHint}</p>
        )}
        {goals.length === 0 ? (
          <span className="muted">No goals assigned.</span>
        ) : (
          <>
            {goals.length !== rootGoals.length && (
              <p className="muted small">
                Showing {rootGoals.length} root goal{rootGoals.length === 1 ? "" : "s"} (
                {goals.length} rows including nested steps).
              </p>
            )}
            <table className="data-table">
              <thead>
                <tr>
                  <th>Goal</th>
                  <th>Status</th>
                  <th>Priority</th>
                  <th>Progress</th>
                  <th>Timing</th>
                  <th className="table-actions-heading" />
                </tr>
              </thead>
              <tbody>
                {rootGoals.map((goal) => {
                  const payloadSummary =
                    goal.goal_type === "travel_to_region"
                      ? formatTravelToRegionDestination(goal, lookups?.regions)
                      : formatGoalPayload(goal.payload);
                  const nested = goalsByParent.get(goal.id) ?? [];
                  const nestedSteps = nested.filter(
                    (child) => child.goal_type !== "travel_segment",
                  );
                  const travelSegmentsForGoal = nested.filter(
                    (child) => child.goal_type === "travel_segment",
                  );
                  return (
                    <tr key={goal.id}>
                      <td>
                        <div>{formatGoalType(goal.goal_type)}</div>
                        <div className="muted small">
                          #{goal.id}
                          {goal.completion_mode ? ` · ${goal.completion_mode}` : ""}
                        </div>
                        {payloadSummary && (
                          <div className="muted small">{payloadSummary}</div>
                        )}
                        {goal.goal_type === "travel_to_region" && (
                          <TravelRoutePreview
                            goalId={goal.id}
                            previewFromRegionId={current.zone?.region_id ?? null}
                            targetRegionId={
                              getPayloadNumber(goal.payload, "region_id") ??
                              getPayloadNumber(goal.payload, "target_region_id")
                            }
                            travelSegments={travelSegmentsForGoal}
                          />
                        )}
                        {goal.goal_type === "travel_to_region" && (
                          <TravelSegmentsList
                            parentId={goal.id}
                            goalsByParent={goalsByParent}
                            busy={busy}
                            onRemoveGoal={(goalId) =>
                              void runEdit(() =>
                                apiDelete<EntityDetail>(
                                  `/entities/${current.id}/goals/${goalId}`,
                                ),
                              )
                            }
                          />
                        )}
                        {nestedSteps.length > 0 && (
                          <div className="goal-nested-roots">
                            {nestedSteps.map((child) => (
                                <GoalNestedBlock
                                  key={child.id}
                                  goal={child}
                                  goalsByParent={goalsByParent}
                                  depth={0}
                                  busy={busy}
                                  entityZoneRegionId={current.zone?.region_id ?? null}
                                  regions={lookups?.regions}
                                  onRemoveGoal={(goalId) =>
                                    void runEdit(() =>
                                      apiDelete<EntityDetail>(
                                        `/entities/${current.id}/goals/${goalId}`,
                                      ),
                                    )
                                  }
                                />
                              ))}
                          </div>
                        )}
                      </td>
                      <td>
                        <Tag tone={goalStatusTone(goal.status)}>
                          {goal.active ? "active" : goal.status}
                        </Tag>
                      </td>
                      <td>
                        <div>{goal.priority}</div>
                        <div className="muted small">Urgency {goal.urgency}</div>
                      </td>
                      <td>
                        <div className="goal-progress">
                          <progress max={100} value={goal.progress} />
                          <span>{formatGoalProgress(goal.progress)}</span>
                        </div>
                      </td>
                      <td>{formatGoalTiming(goal)}</td>
                      <td className="table-actions">
                        <button
                          type="button"
                          disabled={busy}
                          aria-label={`Remove goal ${goal.goal_type}`}
                          onClick={() =>
                            void runEdit(() =>
                              apiDelete<EntityDetail>(
                                `/entities/${current.id}/goals/${goal.id}`,
                              ),
                            )
                          }
                        >
                          x
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </>
        )}
      </Section>

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

function buildGoalHierarchy(goals: EntityGoal[]): {
  rootGoals: EntityGoal[];
  goalsByParent: Map<number, EntityGoal[]>;
} {
  const goalsByParent = new Map<number, EntityGoal[]>();
  const rootGoals: EntityGoal[] = [];
  for (const g of goals) {
    if (g.parent_goal_id == null) {
      rootGoals.push(g);
    } else {
      const pid = g.parent_goal_id;
      if (!goalsByParent.has(pid)) {
        goalsByParent.set(pid, []);
      }
      goalsByParent.get(pid)!.push(g);
    }
  }
  const sortGoals = (a: EntityGoal, b: EntityGoal) => {
    const oa = getPayloadOrder(a.payload);
    const ob = getPayloadOrder(b.payload);
    if (oa !== ob) return oa - ob;
    return a.id - b.id;
  };
  rootGoals.sort(sortGoals);
  for (const arr of goalsByParent.values()) {
    arr.sort(sortGoals);
  }
  return { rootGoals, goalsByParent };
}

function getPayloadOrder(payload: EntityGoal["payload"]): number {
  const n = getPayloadNumber(payload, "order");
  return n ?? 0;
}

function getPayloadString(
  payload: EntityGoal["payload"],
  key: string,
): string | undefined {
  if (!payload) return undefined;
  const v = payload[key];
  return typeof v === "string" && v.length > 0 ? v : undefined;
}

function getPayloadNumber(
  payload: EntityGoal["payload"],
  key: string,
): number | undefined {
  if (!payload) return undefined;
  const v = payload[key];
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  }
  return undefined;
}

function formatTravelToRegionDestination(
  goal: EntityGoal,
  regions: RegionSummary[] | undefined,
): string {
  const id =
    getPayloadNumber(goal.payload, "region_id") ??
    getPayloadNumber(goal.payload, "target_region_id");
  if (id == null) return "";
  const rn = regions?.find((r) => r.id === id)?.name;
  const bits: string[] = [];
  if (rn) bits.push(`Destination: ${rn}`);
  else bits.push(`Destination: region ${id}`);
  const ticks = getPayloadNumber(goal.payload, "duration_ticks");
  if (ticks != null) bits.push(`${ticks} ticks`);
  return bits.join(" · ");
}

function formatTravelSegmentLabel(goal: EntityGoal): string {
  const from = getPayloadString(goal.payload, "from_name");
  const to = getPayloadString(goal.payload, "to_name");
  const fromId = getPayloadNumber(goal.payload, "from_region_id");
  const toId = getPayloadNumber(goal.payload, "to_region_id");
  if (from && to) return `${from} → ${to}`;
  if (fromId != null && toId != null) return `Region ${fromId} → ${toId}`;
  return formatGoalType("travel_segment");
}

function formatTravelSegmentMeta(goal: EntityGoal): string {
  const parts: string[] = [];
  const mode = getPayloadString(goal.payload, "mode");
  const ticks = getPayloadNumber(goal.payload, "duration_ticks");
  if (mode) parts.push(mode);
  if (ticks != null) parts.push(`${ticks} ticks`);
  return parts.join(" · ");
}

function TravelSegmentsList({
  parentId,
  goalsByParent,
  busy,
  onRemoveGoal,
}: {
  parentId: number;
  goalsByParent: Map<number, EntityGoal[]>;
  busy: boolean;
  onRemoveGoal: (goalId: number) => void;
}) {
  const segments = (goalsByParent.get(parentId) ?? []).filter(
    (g) => g.goal_type === "travel_segment",
  );
  if (segments.length === 0) return null;
  return (
    <div className="travel-segments">
      <div className="travel-segments-heading muted small">Route segments</div>
      {segments.map((seg) => (
        <div key={seg.id} className="travel-segment">
          <div className="travel-segment-main">
            <span className="travel-segment-label">{formatTravelSegmentLabel(seg)}</span>
            <Tag tone={goalStatusTone(seg.status)}>
              {seg.active ? "active" : seg.status}
            </Tag>
            <button
              type="button"
              className="travel-segment-remove"
              disabled={busy}
              aria-label={`Remove travel segment ${seg.id}`}
              onClick={() => onRemoveGoal(seg.id)}
            >
              x
            </button>
          </div>
          {formatTravelSegmentMeta(seg) && (
            <div className="travel-segment-meta muted small">
              {formatTravelSegmentMeta(seg)}
            </div>
          )}
          <div className="goal-progress goal-progress-compact">
            <progress max={100} value={seg.progress} />
            <span>{formatGoalProgress(seg.progress)}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

function GoalNestedBlock({
  goal,
  goalsByParent,
  depth,
  busy,
  onRemoveGoal,
  entityZoneRegionId,
  regions,
}: {
  goal: EntityGoal;
  goalsByParent: Map<number, EntityGoal[]>;
  depth: number;
  busy: boolean;
  onRemoveGoal: (goalId: number) => void;
  entityZoneRegionId: number | null;
  regions: RegionSummary[] | undefined;
}) {
  const allKids = goalsByParent.get(goal.id) ?? [];
  const walkKids = allKids.filter((k) => k.goal_type !== "travel_segment");
  const travelSegmentsForGoal = allKids.filter((k) => k.goal_type === "travel_segment");
  const depthClass = `goal-nested-depth-${Math.min(depth, 3)}`;
  const nestedPayloadLine =
    goal.goal_type === "travel_to_region"
      ? formatTravelToRegionDestination(goal, regions)
      : formatGoalPayload(goal.payload);

  return (
    <div className={`goal-nested-block ${depthClass}`}>
      <div className="goal-nested-row">
        <div className="goal-nested-title">
          <span>{formatGoalType(goal.goal_type)}</span>
          <span className="muted small">#{goal.id}</span>
        </div>
        <Tag tone={goalStatusTone(goal.status)}>
          {goal.active ? "active" : goal.status}
        </Tag>
        <div className="goal-progress goal-progress-compact">
          <progress max={100} value={goal.progress} />
          <span>{formatGoalProgress(goal.progress)}</span>
        </div>
        <button
          type="button"
          className="goal-nested-remove"
          disabled={busy}
          aria-label={`Remove goal ${goal.goal_type}`}
          onClick={() => onRemoveGoal(goal.id)}
        >
          x
        </button>
      </div>
      {nestedPayloadLine && (
        <div className="muted small goal-nested-payload">{nestedPayloadLine}</div>
      )}
      {goal.goal_type === "travel_to_region" && (
        <TravelRoutePreview
          goalId={goal.id}
          previewFromRegionId={entityZoneRegionId}
          targetRegionId={
            getPayloadNumber(goal.payload, "region_id") ??
            getPayloadNumber(goal.payload, "target_region_id")
          }
          travelSegments={travelSegmentsForGoal}
        />
      )}
      {goal.goal_type === "travel_to_region" && (
        <TravelSegmentsList
          parentId={goal.id}
          goalsByParent={goalsByParent}
          busy={busy}
          onRemoveGoal={onRemoveGoal}
        />
      )}
      {walkKids.length > 0 && (
        <div className="goal-nested-children">
          {walkKids.map((child) => (
            <GoalNestedBlock
              key={child.id}
              goal={child}
              goalsByParent={goalsByParent}
              depth={depth + 1}
              busy={busy}
              entityZoneRegionId={entityZoneRegionId}
              regions={regions}
              onRemoveGoal={onRemoveGoal}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function opinionTone(value: number): "success" | "danger" | "neutral" {
  if (value > 20) return "success";
  if (value < -20) return "danger";
  return "neutral";
}

function houseRankTone(rank: string): "warning" | "info" | "success" | "neutral" {
  if (rank === "patriarch" || rank === "matriarch") return "warning";
  if (rank === "heir") return "success";
  if (rank === "scion") return "info";
  return "neutral";
}

function goalStatusTone(
  status: EntityGoal["status"],
): "success" | "danger" | "warning" | "info" | "neutral" {
  if (status === "completed") return "success";
  if (status === "failed" || status === "cancelled") return "danger";
  if (status === "active") return "warning";
  if (status === "paused") return "info";
  return "neutral";
}

function formatGoalType(value: string): string {
  return value
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatGoalProgress(value: number): string {
  return `${Math.round(value)}%`;
}

function formatGoalPayload(payload: EntityGoal["payload"]): string {
  if (!payload) return "";
  const parts = Object.entries(payload)
    .filter(([, value]) => value !== null && typeof value !== "object")
    .slice(0, 3)
    .map(([key, value]) => `${formatGoalType(key)}: ${String(value)}`);
  return parts.join(" · ");
}

function formatGoalTiming(goal: EntityGoal): string {
  if (goal.completed_at_game_tick !== null) {
    return `Completed tick ${goal.completed_at_game_tick}`;
  }
  if (goal.paused_at_game_tick !== null) {
    return `Paused tick ${goal.paused_at_game_tick}`;
  }
  if (goal.deadline_game_tick !== null) {
    return `Deadline tick ${goal.deadline_game_tick}`;
  }
  if (goal.started_at_game_tick !== null) {
    return `Started tick ${goal.started_at_game_tick}`;
  }
  return "—";
}

export default EntitiesView;
