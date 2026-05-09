import { useState } from "react";
import "./App.css";
import TopBar from "./components/TopBar";
import Dashboard from "./components/Dashboard";
import EntitiesView from "./components/EntitiesView";
import FactionsView from "./components/FactionsView";
import SchoolsView from "./components/SchoolsView";
import ItemsView from "./components/ItemsView";
import AbilitiesView from "./components/AbilitiesView";
import TraitsView from "./components/TraitsView";
import RacesView from "./components/RacesView";
import Placeholder from "./components/Placeholder";
import { SECTIONS, type SectionId } from "./sections";

function App() {
  const [active, setActive] = useState<SectionId>("dashboard");
  const [refreshKey, setRefreshKey] = useState(0);

  const section = SECTIONS.find((s) => s.id === active);
  const inDashboard = active === "dashboard";

  return (
    <div className="app-shell">
      <div className="bg-decor" aria-hidden="true">
        <div className="bg-orb bg-orb-a" />
        <div className="bg-orb bg-orb-b" />
        <div className="bg-orb bg-orb-c" />
      </div>

      <TopBar
        active={active}
        onChange={setActive}
        onAdvance={() => setRefreshKey((k) => k + 1)}
      />

      <main className="content">
        {!inDashboard && (
          <header className="page-header">
            <h1 className="page-title">{section?.label ?? "Realm"}</h1>
            <div className="page-divider" />
          </header>
        )}
        <div className="content-body">{renderSection(active, refreshKey)}</div>
      </main>
    </div>
  );
}

function renderSection(active: SectionId, refreshKey: number) {
  switch (active) {
    case "dashboard":
      return <Dashboard refreshKey={refreshKey} />;
    case "entities":
      return <EntitiesView refreshKey={refreshKey} />;
    case "factions":
      return <FactionsView refreshKey={refreshKey} />;
    case "schools":
      return <SchoolsView refreshKey={refreshKey} />;
    case "items":
      return <ItemsView refreshKey={refreshKey} />;
    case "abilities":
      return <AbilitiesView refreshKey={refreshKey} />;
    case "traits":
      return <TraitsView refreshKey={refreshKey} />;
    case "races":
      return <RacesView refreshKey={refreshKey} />;
    case "towns":
      return (
        <Placeholder
          title="Towns & settlements"
          description="A future view for towns, regions, and other places. Once the world map and town tables exist, this section will list them with population, controlling faction, and notable buildings."
        />
      );
    default:
      return null;
  }
}

export default App;
