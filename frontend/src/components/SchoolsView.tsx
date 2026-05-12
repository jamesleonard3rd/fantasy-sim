import type { SchoolDetail, SchoolSummary } from "../types";
import { MasterDetail } from "./MasterDetail";
import { Field, Section, Tag } from "./common";

function SchoolsView({ refreshKey }: { refreshKey: number }) {
  return (
    <MasterDetail<SchoolSummary, SchoolDetail>
      key={refreshKey}
      listEndpoint="/schools"
      detailEndpoint={(id) => `/schools/${id}`}
      getId={(s) => s.id}
      getTitle={(s) => s.name}
      getSubtitle={(s) => `Prestige ${s.prestige}`}
      getMeta={(s) =>
        s.capacity == null
          ? `Enrollment ${s.current_enrollment}`
          : `Enrollment ${s.current_enrollment} / ${s.capacity}`
      }
      searchPlaceholder="Search schools…"
      emptyMessage="No schools yet."
      renderDetail={(school) => <SchoolDetailPanel school={school} />}
    />
  );
}

function SchoolDetailPanel({ school }: { school: SchoolDetail }) {
  return (
    <div className="detail">
      <div className="detail-header">
        <div>
          <h2>{school.name}</h2>
          {school.description && (
            <div className="detail-subtitle">{school.description}</div>
          )}
        </div>
        <Tag tone="info">Prestige {school.prestige}</Tag>
      </div>

      <div className="field-grid">
        <Field
          label="Enrollment"
          value={
            school.capacity == null
              ? `${school.current_enrollment} (unlimited)`
              : `${school.current_enrollment} / ${school.capacity}`
          }
        />
        <Field
          label="Enrollment age"
          value={
            school.min_enrollment_age != null && school.max_enrollment_age != null
              ? `${school.min_enrollment_age} – ${school.max_enrollment_age}`
              : "—"
          }
        />
        <Field
          label="Program length"
          value={
            school.enrollment_length != null
              ? `${school.enrollment_length} yrs`
              : "—"
          }
        />
        <Field
          label="Term"
          value={`day ${school.term_start_doy} → ${school.term_end_doy}`}
        />
        <Field
          label="Application deadline"
          value={`day ${school.application_deadline_doy}`}
        />
      </div>

      {school.entry_requirements != null && (
        <Section title="Entry requirements">
          <div className="json-block">
            <pre>{JSON.stringify(school.entry_requirements, null, 2)}</pre>
          </div>
        </Section>
      )}

      <Section title={`Roster (${school.roster.length})`}>
        {school.roster.length === 0 ? (
          <span className="muted">Roster is empty.</span>
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
              {school.roster.map((r) => (
                <tr key={r.entity_id}>
                  <td>{r.name}</td>
                  <td>
                    <Tag tone="neutral">{r.rank}</Tag>
                  </td>
                  <td>{r.reputation}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  );
}

export default SchoolsView;
