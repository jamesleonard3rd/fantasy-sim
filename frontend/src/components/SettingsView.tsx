import { useEffect, useState } from "react";
import { apiGet, apiPatch, apiPost } from "../api";
import type { GameSettings, GameSettingsPatchResponse, SimClock } from "../types";
import { ErrorBox, Loader, Section, Tag } from "./common";

type Props = {
  refreshKey: number;
  simRunning: boolean | null;
  onClockChanged: () => void;
};

function SettingsView({ refreshKey, simRunning, onClockChanged }: Props) {
  const [loading, setLoading] = useState(true);
  const [savingRealm, setSavingRealm] = useState(false);
  const [savingSim, setSavingSim] = useState(false);
  const [error, setError] = useState("");
  const [savedRealm, setSavedRealm] = useState("");
  const [savedSim, setSavedSim] = useState("");
  const [realmDay, setRealmDay] = useState(1);
  const [hour, setHour] = useState(0);
  const [minute, setMinute] = useState(0);
  const [dayLengthMultiplier, setDayLengthMultiplier] = useState(1);
  const [realSecondsPerGameDay, setRealSecondsPerGameDay] = useState(1200);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([apiGet<SimClock>("/sim/clock"), apiGet<GameSettings>("/settings/game-settings")])
      .then(([clock, gs]) => {
        if (cancelled) return;
        setRealmDay(clock.game_day + 1);
        setHour(clock.hour);
        setMinute(clock.minute);
        setRealSecondsPerGameDay(clock.real_seconds_per_game_day);
        const m = gs.simulation?.day_length_multiplier;
        const parsed = typeof m === "number" ? m : Number(m);
        setDayLengthMultiplier(Number.isFinite(parsed) && parsed > 0 ? parsed : 1);
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
    setSavingRealm(true);
    setSavedRealm("");
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
      setRealSecondsPerGameDay(clock.real_seconds_per_game_day);
      setSavedRealm("Realm time updated.");
      onClockChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save realm time.");
    } finally {
      setSavingRealm(false);
    }
  };

  const saveSimulationSettings = async () => {
    setSavingSim(true);
    setSavedSim("");
    setError("");
    try {
      const res = await apiPatch<GameSettingsPatchResponse>("/settings/game-settings", {
        simulation: { day_length_multiplier: dayLengthMultiplier },
      });
      const m = res.settings.simulation?.day_length_multiplier;
      const parsed = typeof m === "number" ? m : Number(m);
      if (Number.isFinite(parsed) && parsed > 0) {
        setDayLengthMultiplier(parsed);
      }
      setRealSecondsPerGameDay(res.real_seconds_per_game_day);
      setSavedSim("Simulation settings saved.");
      onClockChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save simulation settings.");
    } finally {
      setSavingSim(false);
    }
  };

  if (loading) return <Loader label="Loading settings..." />;

  const realMinutesPerRealmDay = realSecondsPerGameDay / 60;

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
                disabled={savingRealm || savingSim}
                onClick={saveRealmTime}
              >
                {savingRealm ? "Saving..." : "Save Time"}
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
            {savedRealm && <div className="settings-success">{savedRealm}</div>}
          </Section>

          <Section title="Simulation">
            <div className="settings-form">
              <label className="settings-field">
                <span>Day length multiplier</span>
                <input
                  type="number"
                  min={0.01}
                  max={1000}
                  step={0.1}
                  value={dayLengthMultiplier}
                  onChange={(event) =>
                    setDayLengthMultiplier(numberFromInput(event.target.value, 1))
                  }
                />
              </label>

              <button
                type="button"
                className="advance-btn settings-save"
                disabled={savingRealm || savingSim}
                onClick={saveSimulationSettings}
              >
                {savingSim ? "Saving..." : "Save simulation"}
              </button>
            </div>

            <div className="settings-hint">
              Baseline is 20 real minutes per full in-game day at multiplier 1. Higher values stretch
              a realm day in real time. Current pace: about {realMinutesPerRealmDay.toFixed(1)} real
              minutes per realm day.
            </div>
            {savedSim && <div className="settings-success">{savedSim}</div>}
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
