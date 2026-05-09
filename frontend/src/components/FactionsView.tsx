import type { FactionDetail, FactionSummary } from "../types";
import { MasterDetail } from "./MasterDetail";
import { Field, Section, Tag } from "./common";

function FactionsView({ refreshKey }: { refreshKey: number }) {
  return (
    <MasterDetail<FactionSummary, FactionDetail>
      key={refreshKey}
      listEndpoint="/factions"
      detailEndpoint={(id) => `/factions/${id}`}
      getId={(f) => f.id}
      getTitle={(f) => f.name}
      getSubtitle={(f) =>
        f.parent_name ? `Sub-faction of ${f.parent_name}` : "Top-level faction"
      }
      getMeta={(f) =>
        `${f.member_count} members · ${f.child_count} children${
          f.is_school ? " · runs a school" : ""
        }`
      }
      searchPlaceholder="Search factions…"
      emptyMessage="No factions yet."
      renderDetail={(faction) => <FactionDetailPanel faction={faction} />}
    />
  );
}

function FactionDetailPanel({ faction }: { faction: FactionDetail }) {
  return (
    <div className="detail">
      <div className="detail-header">
        <div>
          <h2>{faction.name}</h2>
          {faction.description && (
            <div className="detail-subtitle">{faction.description}</div>
          )}
        </div>
        <Tag tone="info">#{faction.id}</Tag>
      </div>

      <div className="field-grid">
        <Field label="Parent" value={faction.parent_name ?? "—"} />
        <Field label="Members" value={faction.members.length} />
        <Field label="Sub-factions" value={faction.children.length} />
        <Field
          label="School?"
          value={faction.school ? <Tag tone="success">Yes</Tag> : "No"}
        />
      </div>

      {faction.school && (
        <Section title="School details">
          <div className="field-grid">
            <Field label="Prestige" value={faction.school.prestige} />
            <Field
              label="Capacity"
              value={
                faction.school.capacity == null
                  ? "Unlimited"
                  : `${faction.school.current_enrollment} / ${faction.school.capacity}`
              }
            />
            <Field
              label="Enrollment age"
              value={
                faction.school.min_enrollment_age != null &&
                faction.school.max_enrollment_age != null
                  ? `${faction.school.min_enrollment_age} – ${faction.school.max_enrollment_age}`
                  : "—"
              }
            />
            <Field
              label="Program length"
              value={
                faction.school.enrollment_length != null
                  ? `${faction.school.enrollment_length} yrs`
                  : "—"
              }
            />
            <Field
              label="Term"
              value={`day ${faction.school.term_start_doy} → ${faction.school.term_end_doy}`}
            />
            <Field
              label="Application deadline"
              value={`day ${faction.school.application_deadline_doy}`}
            />
          </div>
          {faction.school.entry_requirements != null && (
            <div className="json-block">
              <div className="json-label">Entry requirements</div>
              <pre>
                {JSON.stringify(faction.school.entry_requirements, null, 2)}
              </pre>
            </div>
          )}
        </Section>
      )}

      <Section title={`Sub-factions (${faction.children.length})`}>
        {faction.children.length === 0 ? (
          <span className="muted">No sub-factions.</span>
        ) : (
          <ul className="plain-list">
            {faction.children.map((c) => (
              <li key={c.id}>{c.name}</li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={`Members (${faction.members.length})`}>
        {faction.members.length === 0 ? (
          <span className="muted">No members.</span>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Entity</th>
                <th>Rank</th>
                <th>Reputation</th>
              </tr>
            </thead>
            <tbody>
              {faction.members.map((m) => (
                <tr key={m.id}>
                  <td>{m.name}</td>
                  <td>
                    <Tag tone="neutral">{m.rank}</Tag>
                  </td>
                  <td>{m.reputation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  );
}

export default FactionsView;
