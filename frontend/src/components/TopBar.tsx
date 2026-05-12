import { useCallback, useEffect, useRef, useState } from "react";
import { apiGet, apiPost } from "../api";
import {
  GROUPS,
  firstSectionForGroup,
  groupForSection,
  sectionsForGroup,
  type SectionId,
} from "../sections";
import type { SimClock, SimStatus } from "../types";

type Props = {
  active: SectionId;
  onChange: (id: SectionId) => void;
  simRunning: boolean | null;
  onSimRunningChange: (running: boolean) => void;
  clockRefreshKey: number;
};

const TICK_SETTINGS = {
  min_interval_seconds: 15,
  max_interval_seconds: 30,
};

/** While sim runs, clock is extrapolated on the server from last tick. When stopped, no polling — time is static; refetch on mount and when toggling start/stop. */
const CLOCK_POLL_MS_RUNNING = 1000;

function TopBar({
  active,
  onChange,
  simRunning,
  onSimRunningChange,
  clockRefreshKey,
}: Props) {
  const activeGroup = groupForSection(active);
  const subSections = sectionsForGroup(activeGroup);
  const [clock, setClock] = useState<SimClock | null>(null);
  /** Ref updated in the same tick as start/stop so a trailing GET /sim/clock cannot flip us back to "running" while the worker is still dying. */
  const simRunningRef = useRef(false);
  const [busy, setBusy] = useState(false);

  const refreshClock = useCallback(() => {
    apiGet<SimClock>("/sim/clock")
      .then((c) => setClock({ ...c, running: simRunningRef.current }))
      .catch(() => {
        // The rest of the UI already surfaces API errors; keep the top bar quiet.
      });
  }, []);

  useEffect(() => {
    let cancelled = false;
    apiGet<SimClock>("/sim/clock")
      .then((c) => {
        if (cancelled) return;
        simRunningRef.current = c.running;
        onSimRunningChange(c.running);
        setClock(c);
      })
      .catch(() => {
        // keep top bar quiet; main views may surface errors
      });
    return () => {
      cancelled = true;
    };
  }, [onSimRunningChange]);

  useEffect(() => {
    if (simRunning !== true) {
      return;
    }
    const id = window.setInterval(refreshClock, CLOCK_POLL_MS_RUNNING);
    return () => window.clearInterval(id);
  }, [simRunning, refreshClock]);

  useEffect(() => {
    refreshClock();
  }, [clockRefreshKey, refreshClock]);

  const toggleSim = async () => {
    if (simRunning === null) return;
    setBusy(true);
    try {
      const status = simRunning
        ? await apiPost<SimStatus>("/sim/stop")
        : await apiPost<SimStatus>("/sim/start", TICK_SETTINGS);
      simRunningRef.current = status.running;
      onSimRunningChange(status.running);
      refreshClock();
    } catch {
      // Keep the top bar compact; the dashboard still exposes API load errors.
    } finally {
      setBusy(false);
    }
  };

  return (
    <header className="topbar">
      <div className="topbar-row topbar-row-main">
        <div className="topbar-left">
          <div className="brand">
            <div className="brand-crest">FS</div>
            <div className="brand-text">
              <div className="brand-title">Fantasy Sim</div>
              <div className="brand-sub">Realm Console</div>
            </div>
          </div>

          <nav className="primary-nav">
            {GROUPS.map((g) => (
              <PrimaryNavItem
                key={g.id}
                label={g.label}
                active={g.id === activeGroup}
                onClick={() => onChange(firstSectionForGroup(g.id))}
              />
            ))}
          </nav>
        </div>

        <div className="topbar-right">
          <div className="day-chip">
            <div className="day-chip-label">Realm Day</div>
            <div className="day-chip-value">
              {clock ? String(clock.game_day + 1).padStart(3, "0") : "---"}
            </div>
            <div className="day-chip-time">
              {clock ? formatSimTime(clock) : "--:--"}
            </div>
          </div>
          <button
            type="button"
            className="advance-btn sim-toggle-btn"
            disabled={busy || clock === null || simRunning === null}
            onClick={toggleSim}
          >
            <span>
              {busy ? "..." : simRunning ? "Stop Sim" : "Start Sim"}
            </span>
          </button>
        </div>
      </div>

      <div className="topbar-row topbar-row-sub">
        <div className="sub-nav">
          {subSections.map((s) => (
            <SubNavItem
              key={s.id}
              label={s.label}
              active={s.id === active}
              planned={s.status === "planned"}
              onClick={() => onChange(s.id)}
            />
          ))}
        </div>
      </div>
    </header>
  );
}

function formatSimTime(clock: SimClock): string {
  return `${String(clock.hour).padStart(2, "0")}:${String(clock.minute).padStart(2, "0")}`;
}

function PrimaryNavItem({
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
      className={`primary-nav-item ${active ? "is-active" : ""}`}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function SubNavItem({
  label,
  active,
  planned,
  onClick,
}: {
  label: string;
  active: boolean;
  planned: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={`sub-nav-item ${active ? "is-active" : ""}`}
      onClick={onClick}
    >
      <span>{label}</span>
      {planned && <span className="badge-soon">soon</span>}
    </button>
  );
}

export default TopBar;
