import { useEffect, useState } from "react";
import type {
  EntitySummary,
  FactionSummary,
  SchoolSummary,
  Summary,
} from "../types";
import { apiGet } from "../api";
import { ErrorBox, Loader, Tag } from "./common";

type DashboardData = {
  summary: Summary;
  entities: EntitySummary[];
  factions: FactionSummary[];
  schools: SchoolSummary[];
};

const KEY_TILES: { key: keyof Summary; label: string }[] = [
  { key: "entities", label: "Entities" },
  { key: "factions", label: "Factions" },
  { key: "schools", label: "Schools" },
  { key: "items", label: "Items" },
  { key: "abilities", label: "Abilities" },
  { key: "traits", label: "Traits" },
  { key: "relationships", label: "Bonds" },
  { key: "races", label: "Races" },
];

function Dashboard({ refreshKey }: { refreshKey: number }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setData(null);
    setError("");
    Promise.all([
      apiGet<Summary>("/summary"),
      apiGet<EntitySummary[]>("/entities"),
      apiGet<FactionSummary[]>("/factions"),
      apiGet<SchoolSummary[]>("/schools"),
    ])
      .then(([summary, entities, factions, schools]) => {
        if (cancelled) return;
        setData({ summary, entities, factions, schools });
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (error) return <ErrorBox message={error} />;
  if (!data) return <Loader label="Surveying the realm…" />;

  const { summary, entities, factions, schools } = data;
  const featured = entities[0];
  const recentEntities = entities.slice(0, 6);
  const topFactions = [...factions]
    .sort((a, b) => b.member_count - a.member_count || a.name.localeCompare(b.name))
    .slice(0, 6);
  const sortedSchools = [...schools].sort((a, b) => b.prestige - a.prestige);

  return (
    <div className="dash">
      <section className="dash-hero panel">
        <div className="hero-glow" />
        <div className="hero-text">
          <div className="hero-eyebrow">State of the Realm</div>
          <h1 className="hero-title">
            {entities.length} souls walk the world.
          </h1>
          <p className="hero-sub">
            {factions.length} factions vie for power across {schools.length}{" "}
            schools, bound by {summary.relationships} relationships.
          </p>
        </div>
        <div className="hero-stats">
          {KEY_TILES.map((t) => (
            <div className="hero-stat" key={t.key}>
              <div className="hero-stat-value">{summary[t.key] ?? 0}</div>
              <div className="hero-stat-label">{t.label}</div>
            </div>
          ))}
        </div>
      </section>

      <div className="dash-grid">
        <section className="panel widget">
          <header className="widget-header">
            <h3>Decrees & Tidings</h3>
            <span className="muted">Recent activity</span>
          </header>
          <ul className="news-list">
            <NewsItem
              tone="info"
              title="World seeded with template entities"
              meta={`${entities.length} entities are now alive in the world.`}
            />
            <NewsItem
              tone="success"
              title={`${schools.length} schools have opened their gates`}
              meta={
                sortedSchools[0]
                  ? `Highest prestige: ${sortedSchools[0].name} (${sortedSchools[0].prestige})`
                  : ""
              }
            />
            <NewsItem
              tone="warning"
              title="Towns & settlements pending"
              meta="The Realm tab will fill in once the world map is implemented."
            />
            <NewsItem
              tone="neutral"
              title="API connected"
              meta="Live state served from FastAPI on :8000."
            />
          </ul>
        </section>

        <section className="panel widget">
          <header className="widget-header">
            <h3>Featured Entity</h3>
            {featured && <Tag tone="info">#{featured.id}</Tag>}
          </header>
          {featured ? (
            <div className="featured">
              <div className="featured-portrait">
                {initials(featured.name)}
              </div>
              <div className="featured-meta">
                <div className="featured-name">{featured.name}</div>
                <div className="featured-sub muted">
                  {[featured.race, featured.subrace]
                    .filter(Boolean)
                    .join(" · ") || featured.type}
                </div>
              </div>
              <div className="featured-tags">
                {featured.zone && (
                  <Tag tone="neutral">Zone: {featured.zone}</Tag>
                )}
                <Tag tone="success">{featured.type}</Tag>
              </div>
              <div className="featured-roster">
                <div className="muted small">Other notable figures</div>
                <ul className="plain-list">
                  {recentEntities.slice(1).map((e) => (
                    <li key={e.id}>
                      <strong>{e.name}</strong>{" "}
                      <span className="muted small">
                        {[e.race, e.subrace].filter(Boolean).join(" · ")}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <div className="muted">No entities seeded yet.</div>
          )}
        </section>

        <section className="panel widget">
          <header className="widget-header">
            <h3>Faction Standings</h3>
            <span className="muted small">By member count</span>
          </header>
          {topFactions.length === 0 ? (
            <div className="muted">No factions yet.</div>
          ) : (
            <table className="standings">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Faction</th>
                  <th>Members</th>
                  <th>Sub</th>
                </tr>
              </thead>
              <tbody>
                {topFactions.map((f, idx) => (
                  <tr key={f.id}>
                    <td className="standings-rank">{idx + 1}</td>
                    <td>
                      <div className="faction-cell">
                        <span
                          className="faction-bullet"
                          style={{ background: bulletColor(idx) }}
                        />
                        <div>
                          <div>{f.name}</div>
                          {f.parent_name && (
                            <div className="muted small">
                              of {f.parent_name}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td>{f.member_count}</td>
                    <td>{f.child_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="panel widget widget-wide">
          <header className="widget-header">
            <h3>Schools of the Realm</h3>
            <span className="muted small">Sorted by prestige</span>
          </header>
          {sortedSchools.length === 0 ? (
            <div className="muted">No schools have been founded.</div>
          ) : (
            <div className="school-grid">
              {sortedSchools.map((s) => (
                <div className="school-card" key={s.id}>
                  <div className="school-card-top">
                    <div className="school-name">{s.name}</div>
                    <div className="school-prestige">★ {s.prestige}</div>
                  </div>
                  <div className="school-meta">
                    <span>
                      {s.capacity == null
                        ? `${s.current_enrollment} enrolled`
                        : `${s.current_enrollment} / ${s.capacity} seats`}
                    </span>
                    <span className="muted">
                      Term: day {s.term_start_doy}–{s.term_end_doy}
                    </span>
                  </div>
                  <div className="school-bar">
                    <div
                      className="school-bar-fill"
                      style={{
                        width: `${capacityPct(
                          s.current_enrollment,
                          s.capacity,
                        )}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function NewsItem({
  tone,
  title,
  meta,
}: {
  tone: "info" | "success" | "warning" | "neutral";
  title: string;
  meta?: string;
}) {
  return (
    <li className="news-item">
      <span className={`news-dot news-dot-${tone}`} />
      <div className="news-body">
        <div className="news-title">{title}</div>
        {meta && <div className="muted small">{meta}</div>}
      </div>
    </li>
  );
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function bulletColor(idx: number): string {
  const palette = [
    "#a855f7",
    "#fbbf24",
    "#22d3ee",
    "#34d399",
    "#f472b6",
    "#f97316",
  ];
  return palette[idx % palette.length];
}

function capacityPct(current: number, capacity: number | null): number {
  if (capacity == null || capacity <= 0) return Math.min(100, current * 5);
  return Math.min(100, Math.round((current / capacity) * 100));
}

export default Dashboard;
