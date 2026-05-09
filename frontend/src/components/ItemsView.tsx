import { useEffect, useMemo, useState } from "react";
import type { Item } from "../types";
import { apiGet } from "../api";
import { EmptyState, ErrorBox, Loader, Tag } from "./common";

const CATEGORY_ORDER = ["weapon", "armor", "consumable"];

function ItemsView({ refreshKey }: { refreshKey: number }) {
  const [items, setItems] = useState<Item[] | null>(null);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | "all">("all");

  useEffect(() => {
    let cancelled = false;
    setItems(null);
    setError("");
    apiGet<Item[]>("/items")
      .then((data) => !cancelled && setItems(data))
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const categories = useMemo(() => {
    if (!items) return [] as string[];
    const set = new Set<string>();
    for (const i of items) {
      if (i.category) set.add(i.category);
    }
    const known = CATEGORY_ORDER.filter((c) => set.has(c));
    const extras = [...set].filter((c) => !CATEGORY_ORDER.includes(c)).sort();
    return [...known, ...extras];
  }, [items]);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = query.trim().toLowerCase();
    return items.filter((i) => {
      if (activeCategory !== "all" && (i.category ?? "") !== activeCategory) {
        return false;
      }
      if (!q) return true;
      return (
        i.name.toLowerCase().includes(q) ||
        (i.description ?? "").toLowerCase().includes(q)
      );
    });
  }, [items, query, activeCategory]);

  if (error) return <ErrorBox message={error} />;
  if (!items) return <Loader />;

  return (
    <div className="catalog">
      <div className="catalog-toolbar">
        <input
          className="search-input"
          placeholder="Search items…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <div className="filter-row">
          <FilterChip
            label={`All (${items.length})`}
            active={activeCategory === "all"}
            onClick={() => setActiveCategory("all")}
          />
          {categories.map((c) => {
            const count = items.filter((i) => i.category === c).length;
            return (
              <FilterChip
                key={c}
                label={`${prettyCategory(c)} (${count})`}
                active={activeCategory === c}
                onClick={() => setActiveCategory(c)}
              />
            );
          })}
        </div>
      </div>

      {filtered.length === 0 ? (
        <EmptyState message="No items match." />
      ) : (
        <div className="card-grid">
          {filtered.map((item) => (
            <article key={item.id} className="card">
              <header className="card-header">
                <h3>{item.name}</h3>
                {item.category && (
                  <Tag tone={categoryTone(item.category)}>
                    {prettyCategory(item.category)}
                  </Tag>
                )}
              </header>
              {item.description && (
                <p className="card-body">{item.description}</p>
              )}
              <footer className="card-footer">
                <span className="muted">#{item.id}</span>
                <span>Owned: {item.total_owned}</span>
              </footer>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`filter-chip ${active ? "is-active" : ""}`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function prettyCategory(c: string) {
  return c.charAt(0).toUpperCase() + c.slice(1);
}

function categoryTone(c: string): "danger" | "info" | "success" | "neutral" {
  if (c === "weapon") return "danger";
  if (c === "armor") return "info";
  if (c === "consumable") return "success";
  return "neutral";
}

export default ItemsView;
