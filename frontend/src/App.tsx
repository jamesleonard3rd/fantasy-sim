import "./App.css";
import RefreshButton from "./components/RefreshButton";
import { useState } from "react";

type Entity = {
  id: number;
  name: string;
  type: string;
};

function App() {
  const [entities, setEntities] = useState<Entity[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  async function handleRefresh() {
    setLoading(true);
    setError("");

    try {
      const data = await fetchEntities();
      setEntities(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch entities.");
    } finally {
      setLoading(false);
    }
  }

  async function fetchEntities() {
    const res = await fetch("http://localhost:8000/entities");
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status}`);
    }

    return (await res.json()) as Entity[];
  }

  return (
    <div className="app">
      <h1 className="title">Game State Manager</h1>
      <RefreshButton onClick={handleRefresh} />
      {loading && <p>Loading entities...</p>}
      {error && <p className="error-text">{error}</p>}

      <div className="entity-list">
        {entities.length === 0 ? (
          <p className="empty-text">Press Refresh to load entities.</p>
        ) : (
          entities.map((entity) => (
            <div key={entity.id} className="entity-card">
              <p>
                <strong>ID:</strong> {entity.id}
              </p>
              <p>
                <strong>Name:</strong> {entity.name}
              </p>
              <p>
                <strong>Type:</strong> {entity.type}
              </p>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

export default App;
