import { useEffect, useState } from "react";
import { apiGet, apiPost } from "../api";
import type { SimClock } from "../types";
import { ErrorBox, Loader, Section, Tag } from "./common";

type Props = {
  refreshKey: number;
  simRunning: boolean | null;
  onClockChanged: () => void;
};

function SettingsView({ refreshKey, simRunning, onClockChanged }: Props) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState("");
  const [realmDay, setRealmDay] = useState(1);
  const [hour, setHour] = useState(0);
  const [minute, setMinute] = useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    apiGet<SimClock>("/sim/clock")
      .then((clock) => {
        if (cancelled) return;
        setRealmDay(clock.game_day + 1);
        setHour(clock.hour);
        setMinute(clock.minute);
        setError("");
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  const saveRealmTime = async () => {
    setSaving(true);
    setSaved("");
    setError("");
    try {
      const clock = await apiPost<SimClock>("/settings/realm-time", {
        game_day: Math.max(0, Math.floor(realmDay) - 1),
        hour: clampInt(hour, 0, 23),
        minute: clampInt(minute, 0, 59),
      });
      setRealmDay(clock.game_day + 1);
      setHour(clock.hour);
      setMinute(clock.minute);
      setSaved("Realm time updated.");
      onClockChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save realm time.");
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <Loader label="Loading settings..." />;

  return (
    <div className="settings-page">
      {error && <ErrorBox message={error} />}

      <section className="panel settings-panel">
        <div className="detail">
          <div className="detail-header">
            <div>
              <h2>Game Settings</h2>
              <div className="detail-subtitle">
                Direct controls for realm-wide simulation state.
              </div>
            </div>
            <Tag tone={simRunning ? "success" : "neutral"}>
              {simRunning ? "Sim running" : "Sim stopped"}
            </Tag>
          </div>

          <Section title="Realm Time">
            <div className="settings-form">
              <label className="settings-field">
                <span>Realm day</span>
                <input
                  type="number"
                  min={1}
                  value={realmDay}
                  onChange={(event) => setRealmDay(numberFromInput(event.target.value, 1))}
                />
              </label>

              <label className="settings-field">
                <span>Hour</span>
                <input
                  type="number"
                  min={0}
                  max={23}
                  value={hour}
                  onChange={(event) => setHour(numberFromInput(event.target.value, 0))}
                />
              </label>

              <label className="settings-field">
                <span>Minute</span>
                <input
                  type="number"
                  min={0}
                  max={59}
                  value={minute}
                  onChange={(event) => setMinute(numberFromInput(event.target.value, 0))}
                />
              </label>

              <button
                type="button"
                className="advance-btn settings-save"
                disabled={saving}
                onClick={saveRealmTime}
              >
                {saving ? "Saving..." : "Save Time"}
              </button>
            </div>

            <div className="settings-hint">
              Current target: day {String(Math.max(1, realmDay)).padStart(3, "0")} at{" "}
              {String(clampInt(hour, 0, 23)).padStart(2, "0")}:
              {String(clampInt(minute, 0, 59)).padStart(2, "0")}
            </div>
            {simRunning && (
              <div className="settings-hint">
                The sim is running, so time will continue advancing after save.
              </div>
            )}
            {saved && <div className="settings-success">{saved}</div>}
          </Section>
        </div>
      </section>
    </div>
  );
}

function numberFromInput(value: string, fallback: number): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function clampInt(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, Math.floor(value)));
}

export default SettingsView;
