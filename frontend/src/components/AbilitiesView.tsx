import { useEffect, useMemo, useState } from "react";
import type { Ability } from "../types";
import { apiGet } from "../api";
import { EmptyState, ErrorBox, Loader, Tag } from "./common";

function AbilitiesView({ refreshKey }: { refreshKey: number }) {
  const [abilities, setAbilities] = useState<Ability[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;
    setAbilities(null);
    setError("");
    apiGet<Ability[]>("/abilities")
      .then((data) => !cancelled && setAbilities(data))
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const filtered = useMemo(() => {
    if (!abilities) return [];
    const q = query.trim().toLowerCase();
    if (!q) return abilities;
    return abilities.filter(
      (a) =>
        a.name.toLowerCase().includes(q) ||
        (a.description ?? "").toLowerCase().includes(q) ||
        a.type.toLowerCase().includes(q),
    );
  }, [abilities, query]);

  if (error) return <ErrorBox message={error} />;
  if (!abilities) return <Loader />;

  return (
    <div className="catalog">
      <div className="catalog-toolbar">
        <input
          className="search-input"
          placeholder="Search abilities…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className="muted">{filtered.length} / {abilities.length}</span>
      </div>

      {filtered.length === 0 ? (
        <EmptyState message="No abilities match." />
      ) : (
        <table className="data-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Cost</th>
              <th>Damage</th>
              <th>Cooldown</th>
              <th>Holders</th>
              <th>Description</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((a) => (
              <tr key={a.id}>
                <td><strong>{a.name}</strong></td>
                <td>
                  <Tag tone={a.type === "active" ? "warning" : "neutral"}>
                    {a.type}
                  </Tag>
                </td>
                <td>{a.cost}</td>
                <td>{a.damage}</td>
                <td>{a.cooldown_seconds}s</td>
                <td>{a.holders}</td>
                <td className="muted small">{a.description ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default AbilitiesView;
