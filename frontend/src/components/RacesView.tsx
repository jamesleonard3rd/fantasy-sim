import { useEffect, useState } from "react";
import type { Race } from "../types";
import { apiGet } from "../api";
import { EmptyState, ErrorBox, Loader, Tag } from "./common";

function RacesView({ refreshKey }: { refreshKey: number }) {
  const [races, setRaces] = useState<Race[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setRaces(null);
    setError("");
    apiGet<Race[]>("/races")
      .then((data) => !cancelled && setRaces(data))
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (error) return <ErrorBox message={error} />;
  if (!races) return <Loader />;
  if (races.length === 0) return <EmptyState message="No races defined." />;

  return (
    <div className="card-grid">
      {races.map((r) => (
        <article key={r.id} className="card">
          <header className="card-header">
            <h3>{r.name}</h3>
            <Tag tone="info">{r.entity_count} entities</Tag>
          </header>
          <div className="card-meta">
            <div className="meta-label">Subraces ({r.subraces.length})</div>
            {r.subraces.length === 0 ? (
              <span className="muted">None.</span>
            ) : (
              <div className="chip-row">
                {r.subraces.map((s) => (
                  <Tag key={s.id} tone="neutral">
                    {s.name}
                  </Tag>
                ))}
              </div>
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

export default RacesView;
