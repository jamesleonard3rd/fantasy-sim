import type { EntityDetail, EntitySummary } from "../types";
import { MasterDetail } from "./MasterDetail";
import { Field, Section, Tag, formatDate } from "./common";

function EntitiesView({ refreshKey }: { refreshKey: number }) {
  return (
    <MasterDetail<EntitySummary, EntityDetail>
      key={refreshKey}
      listEndpoint="/entities"
      detailEndpoint={(id) => `/entities/${id}`}
      getId={(e) => e.id}
      getTitle={(e) => e.name}
      getSubtitle={(e) =>
        [e.race, e.subrace].filter(Boolean).join(" · ") || e.type
      }
      getMeta={(e) => `#${e.id}${e.zone ? ` · ${e.zone}` : ""}`}
      searchPlaceholder="Search entities by name, race, zone…"
      emptyMessage="No entities yet. Try seeding the database."
      renderDetail={(entity) => <EntityDetailPanel entity={entity} />}
    />
  );
}

function EntityDetailPanel({ entity }: { entity: EntityDetail }) {
  return (
    <div className="detail">
      <div className="detail-header">
        <div>
          <h2>{entity.name}</h2>
          <div className="detail-subtitle">
            {[entity.race, entity.subrace].filter(Boolean).join(" · ") ||
              entity.type}
          </div>
        </div>
        <Tag tone="info">#{entity.id}</Tag>
      </div>

      <div className="field-grid">
        <Field label="Type" value={entity.type} />
        <Field label="Race" value={entity.race ?? "—"} />
        <Field label="Subrace" value={entity.subrace ?? "—"} />
        <Field label="Zone" value={entity.zone?.zone ?? "—"} />
        <Field
          label="Position"
          value={
            entity.position
              ? `(${entity.position.x}, ${entity.position.y}, ${entity.position.z})`
              : "—"
          }
        />
        <Field label="Created" value={formatDate(entity.created_at)} />
      </div>

      <Section title={`Traits (${entity.traits.length})`}>
        {entity.traits.length === 0 ? (
          <span className="muted">No traits.</span>
        ) : (
          <div className="chip-row">
            {entity.traits.map((t) => (
              <Tag key={t.id} tone="info">
                {t.name}
              </Tag>
            ))}
          </div>
        )}
      </Section>

      <Section title={`Factions (${entity.factions.length})`}>
        {entity.factions.length === 0 ? (
          <span className="muted">Not affiliated.</span>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Faction</th>
                <th>Rank</th>
                <th>Reputation</th>
              </tr>
            </thead>
            <tbody>
              {entity.factions.map((f) => (
                <tr key={f.id}>
                  <td>{f.name}</td>
                  <td>
                    <Tag tone="neutral">{f.rank}</Tag>
                  </td>
                  <td>{f.reputation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title={`Schools (${entity.schools.length})`}>
        {entity.schools.length === 0 ? (
          <span className="muted">Not enrolled in any school.</span>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>School</th>
                <th>Status</th>
                <th>Enrolled</th>
              </tr>
            </thead>
            <tbody>
              {entity.schools.map((s) => (
                <tr key={s.school_id}>
                  <td>{s.school_name}</td>
                  <td>
                    <Tag tone="info">{s.status}</Tag>
                  </td>
                  <td>{s.enrolled_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title={`Inventory (${entity.items.length})`}>
        {entity.items.length === 0 ? (
          <span className="muted">Empty inventory.</span>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Item</th>
                <th>Category</th>
                <th>Qty</th>
              </tr>
            </thead>
            <tbody>
              {entity.items.map((it) => (
                <tr key={it.id}>
                  <td>
                    <div>{it.name}</div>
                    {it.description && (
                      <div className="muted small">{it.description}</div>
                    )}
                  </td>
                  <td>{it.category ?? "—"}</td>
                  <td>{it.quantity}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title={`Abilities (${entity.abilities.length})`}>
        {entity.abilities.length === 0 ? (
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
              </tr>
            </thead>
            <tbody>
              {entity.abilities.map((a) => (
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
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      <Section title={`Relationships (${entity.relationships.length})`}>
        {entity.relationships.length === 0 ? (
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
              {entity.relationships.map((r) => (
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

function opinionTone(value: number): "success" | "danger" | "neutral" {
  if (value > 20) return "success";
  if (value < -20) return "danger";
  return "neutral";
}

export default EntitiesView;
