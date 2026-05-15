import type { HouseDetail, HouseMember, HouseSummary } from "../types";
import { MasterDetail } from "./MasterDetail";
import { Field, Section, Tag, formatDate } from "./common";

function HousesView({ refreshKey }: { refreshKey: number }) {
  return (
    <MasterDetail<HouseSummary, HouseDetail>
      key={refreshKey}
      listEndpoint="/houses"
      detailEndpoint={(id) => `/houses/${id}`}
      getId={(h) => h.id}
      getTitle={(h) => h.name}
      getSubtitle={(h) =>
        h.type ? `${capitalize(h.type)} house` : "House"
      }
      getMeta={(h) =>
        `${h.member_count} member${h.member_count === 1 ? "" : "s"}${
          h.spawn_min != null ? ` · spawn min ${h.spawn_min}` : ""
        }`
      }
      searchPlaceholder="Search houses…"
      emptyMessage="No houses yet."
      renderDetail={(house) => <HouseDetailPanel house={house} />}
    />
  );
}

function HouseDetailPanel({ house }: { house: HouseDetail }) {
  const sortedMembers = sortMembers(house.members);
  const head = sortedMembers.find(
    (m) => m.rank === "patriarch" || m.rank === "matriarch",
  );

  return (
    <div className="detail">
      <div className="detail-header">
        <div>
          <h2>{house.name}</h2>
          <div className="detail-subtitle">
            {[
              house.type ? `${capitalize(house.type)} house` : null,
              house.default_surname ? `Surname: ${house.default_surname}` : null,
            ]
              .filter(Boolean)
              .join(" · ") || "House"}
          </div>
        </div>
        <Tag tone="info">#{house.id}</Tag>
      </div>

      {house.notes && <p className="house-notes">{house.notes}</p>}

      <div className="field-grid">
        <Field
          label="Head of House"
          value={
            head ? (
              <span>
                {head.name}{" "}
                <span className="muted small">({head.rank})</span>
              </span>
            ) : (
              "—"
            )
          }
        />
        <Field label="Members" value={sortedMembers.length} />
        <Field
          label="Spawn minimum"
          value={house.spawn_min != null ? house.spawn_min : "—"}
        />
        <Field
          label="Default surname"
          value={house.default_surname ?? "—"}
        />
      </div>

      <Section title={`Members (${sortedMembers.length})`}>
        {sortedMembers.length === 0 ? (
          <span className="muted">No members in this house yet.</span>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Member</th>
                <th>Rank</th>
                <th>Race</th>
                <th>Joined</th>
              </tr>
            </thead>
            <tbody>
              {sortedMembers.map((m) => (
                <tr key={m.id}>
                  <td>{m.name}</td>
                  <td>
                    <Tag tone={rankTone(m.rank)}>{m.rank}</Tag>
                  </td>
                  <td>
                    {[m.race, m.subrace].filter(Boolean).join(" · ") || "—"}
                  </td>
                  <td>{formatDate(m.joined_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>

      {(house.forced_traits?.length ?? 0) > 0 && (
        <Section title="Bloodline traits">
          <div className="chip-row">
            {(house.forced_traits ?? []).map((t) => (
              <Tag key={t} tone="warning">
                {t}
              </Tag>
            ))}
          </div>
        </Section>
      )}

      {(house.forced_magic?.length ?? 0) > 0 && (
        <Section title="Bloodline magic">
          <div className="chip-row">
            {(house.forced_magic ?? []).map((m) => (
              <Tag key={m} tone="info">
                {m}
              </Tag>
            ))}
          </div>
        </Section>
      )}

      {house.affiliated_factions.length > 0 && (
        <Section
          title={`Other organizations (${house.affiliated_factions.length})`}
        >
          <div className="muted small" style={{ marginBottom: 8 }}>
            Factions, orders and guilds members of this house belong to.
          </div>
          <table className="data-table">
            <thead>
              <tr>
                <th>Organization</th>
                <th>Kind</th>
                <th>Members from this house</th>
              </tr>
            </thead>
            <tbody>
              {house.affiliated_factions.map((f) => (
                <tr key={f.id}>
                  <td>{f.name}</td>
                  <td>
                    <Tag tone="neutral">{capitalize(f.kind)}</Tag>
                  </td>
                  <td>{f.member_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}

      <Section title="Generation rules">
        <div className="field-grid">
          <Field
            label="House trait counts"
            value={renderWeightMap(house.house_trait_counts)}
          />
          <Field
            label="House trait weights"
            value={renderWeightMap(house.house_trait_weights)}
          />
          <Field
            label="Trait weight multipliers"
            value={renderWeightMap(house.normal_trait_weight_mults)}
          />
          <Field
            label="Magic type counts"
            value={renderWeightMap(house.magic_type_counts)}
          />
          <Field
            label="Magic weights"
            value={renderWeightMap(house.magic_weights)}
          />
        </div>
      </Section>
    </div>
  );
}

function renderWeightMap(map: Record<string, number> | null) {
  if (!map || Object.keys(map).length === 0) {
    return <span className="muted">—</span>;
  }
  return (
    <div className="chip-row">
      {Object.entries(map).map(([key, value]) => (
        <Tag key={key} tone="neutral">
          {key}: {value}
        </Tag>
      ))}
    </div>
  );
}

function sortMembers(members: HouseMember[]): HouseMember[] {
  const order: Record<string, number> = {
    patriarch: 0,
    matriarch: 0,
    heir: 1,
    scion: 2,
    member: 3,
  };
  return [...members].sort((a, b) => {
    const ra = order[a.rank] ?? 99;
    const rb = order[b.rank] ?? 99;
    if (ra !== rb) return ra - rb;
    return a.name.localeCompare(b.name);
  });
}

function rankTone(rank: string): "warning" | "info" | "success" | "neutral" {
  if (rank === "patriarch" || rank === "matriarch") return "warning";
  if (rank === "heir") return "success";
  if (rank === "scion") return "info";
  return "neutral";
}

function capitalize(value: string): string {
  if (!value) return value;
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export default HousesView;
