import { useEffect, useMemo, useState } from "react";
import type { Trait } from "../types";
import { apiGet } from "../api";
import { EmptyState, ErrorBox, Loader, Tag } from "./common";

function TraitsView({ refreshKey }: { refreshKey: number }) {
  const [traits, setTraits] = useState<Trait[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    setTraits(null);
    setError("");
    apiGet<Trait[]>("/traits")
      .then((data) => !cancelled && setTraits(data))
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const filtered = useMemo(() => {
    if (!traits) return [];
    const q = query.trim().toLowerCase();
    if (!q) return traits;
    return traits.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        (t.description ?? "").toLowerCase().includes(q),
    );
  }, [traits, query]);

  if (error) return <ErrorBox message={error} />;
  if (!traits) return <Loader />;

  return (
    <div className="catalog">
      <div className="catalog-toolbar">
        <input
          className="search-input"
          placeholder="Search traits…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="muted">{filtered.length} / {traits.length}</span>
      </div>

      {filtered.length === 0 ? (
        <EmptyState message="No traits match." />
      ) : (
        <div className="card-grid">
          {filtered.map((t) => (
            <article key={t.id} className="card">
              <header className="card-header">
                <h3>{t.name}</h3>
                <Tag tone="info">{t.holders} holders</Tag>
              </header>
              {t.description && <p className="card-body">{t.description}</p>}
              {t.modifiers.length > 0 && (
                <div className="card-meta">
                  <div className="meta-label">Stat modifiers</div>
                  <div className="chip-row">
                    {t.modifiers.map((m, idx) => (
                      <Tag
                        key={`${m.stat}-${idx}`}
                        tone={m.value >= 0 ? "success" : "danger"}
                      >
                        {m.stat} {formatModifier(m)}
                      </Tag>
                    ))}
                  </div>
                </div>
              )}
              {t.grants_abilities.length > 0 && (
                <div className="card-meta">
                  <div className="meta-label">Grants abilities</div>
                  <div className="chip-row">
                    {t.grants_abilities.map((a) => (
                      <Tag key={a.id} tone="warning">
                        {a.name}
                      </Tag>
                    ))}
                  </div>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function formatModifier(m: { type: "add" | "mult"; value: number }) {
  if (m.type === "mult") return `×${m.value}`;
  return m.value >= 0 ? `+${m.value}` : `${m.value}`;
}

export default TraitsView;
