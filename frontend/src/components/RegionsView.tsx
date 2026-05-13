import type { RegionDetail, RegionSummary } from "../types";
import { MasterDetail } from "./MasterDetail";
import { Field, Section, Tag, formatDate } from "./common";

const REGION_REFRESH_MS_RUNNING = 3000;

function RegionsView({
  refreshKey,
  simRunning,
}: {
  refreshKey: number;
  simRunning: boolean | null;
}) {
  return (
    <MasterDetail<RegionSummary, RegionDetail>
      key={refreshKey}
      listEndpoint="/regions"
      detailEndpoint={(id) => `/regions/${id}`}
      refreshIntervalMs={simRunning === true ? REGION_REFRESH_MS_RUNNING : undefined}
      getId={(r) => r.id}
      getTitle={(r) => r.name}
      getSubtitle={(r) => {
        const parentLabel = r.parent_name ? `Subregion of ${r.parent_name}` : null;
        return [capitalize(r.type), parentLabel].filter(Boolean).join(" · ");
      }}
      getMeta={(r) =>
        `${r.total_entity_count} resident${r.total_entity_count === 1 ? "" : "s"} total · ${r.child_count} subregion${r.child_count === 1 ? "" : "s"}`
      }
      searchPlaceholder="Search regions…"
      emptyMessage="No regions yet. Seed game data and run seed-regions."
      renderDetail={(region) => <RegionDetailPanel region={region} />}
    />
  );
}

function capitalize(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function RegionDetailPanel({ region }: { region: RegionDetail }) {
  return (
    <div className="detail">
      <div className="detail-header">
        <div>
          <h2>{region.name}</h2>
          <div className="detail-subtitle">
            Simulation partition · {capitalize(region.type)}
          </div>
        </div>
        <div className="chip-row">
          <Tag tone={region.paused ? "warning" : "success"}>
            {region.paused ? "Paused" : "Live"}
          </Tag>
          <Tag tone="info">#{region.id}</Tag>
        </div>
      </div>

      <div className="field-grid">
        <Field
          label="Type"
          value={capitalize(region.type)}
        />
        <Field
          label="Parent"
          value={region.parent_name ?? "—"}
        />
        <Field
          label="Last tick"
          value={
            region.last_tick_at ? formatDate(region.last_tick_at) : "—"
          }
        />
        <Field label="Direct residents" value={region.direct_entity_count} />
        <Field label="Total residents" value={region.total_entity_count} />
      </div>

      <Section title={`Subregions (${region.children.length})`}>
        {region.children.length === 0 ? (
          <span className="muted">No subregions.</span>
        ) : (
          <ul className="plain-list">
            {region.children.map((child) => (
              <li key={child.id}>
                <strong>{child.name}</strong>{" "}
                <span className="muted small">{capitalize(child.type)}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title={`Present in region and subregions (${region.residents.length})`}>
        {region.residents.length === 0 ? (
          <span className="muted">No entities are zoned here yet.</span>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Entity</th>
                <th>Location</th>
                <th>Zone label</th>
              </tr>
            </thead>
            <tbody>
              {region.residents.map((row) => (
                <tr key={row.id}>
                  <td>{row.name}</td>
                  <td>
                    {row.region_name}
                    {row.region_id !== region.id && (
                      <span className="muted small"> · {capitalize(row.region_type)}</span>
                    )}
                  </td>
                  <td>{row.zone}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  );
}

export default RegionsView;
