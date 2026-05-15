import { useEffect, useMemo, useState } from "react";
import { apiGet } from "../api";
import type { EntityGoal } from "../types";

type TravelRouteApi = {
  segments: unknown[] | null;
  stop_names: string[];
  reason: string | null;
};

function getPayloadNumber(
  payload: EntityGoal["payload"],
  key: string,
): number | undefined {
  if (!payload) return undefined;
  const v = payload[key];
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string" && v.trim() !== "") {
    const n = Number(v);
    return Number.isFinite(n) ? n : undefined;
  }
  return undefined;
}

function getPayloadString(
  payload: EntityGoal["payload"],
  key: string,
): string | undefined {
  if (!payload) return undefined;
  const v = payload[key];
  return typeof v === "string" && v.length > 0 ? v : undefined;
}

function sortTravelSegments(segments: EntityGoal[]): EntityGoal[] {
  return [...segments].sort((a, b) => {
    const oa = getPayloadNumber(a.payload, "order") ?? 0;
    const ob = getPayloadNumber(b.payload, "order") ?? 0;
    if (oa !== ob) return oa - ob;
    return a.id - b.id;
  });
}

function stopLineFromSegmentGoals(sorted: EntityGoal[]): string | null {
  if (sorted.length === 0) return null;
  const parts: string[] = [];
  const p0 = sorted[0].payload;
  const firstFrom =
    getPayloadString(p0, "from_name") ??
    (() => {
      const id = getPayloadNumber(p0, "from_region_id");
      return id != null ? `Region ${id}` : undefined;
    })();
  if (firstFrom) parts.push(firstFrom);
  for (const seg of sorted) {
    const p = seg.payload;
    const to =
      getPayloadString(p, "to_name") ??
      (() => {
        const id = getPayloadNumber(p, "to_region_id");
        return id != null ? `Region ${id}` : undefined;
      })();
    if (to) parts.push(to);
  }
  return parts.length >= 2 ? parts.join(" → ") : parts.length === 1 ? parts[0] : null;
}

export function TravelRoutePreview({
  goalId,
  previewFromRegionId,
  targetRegionId,
  travelSegments,
}: {
  goalId: number;
  previewFromRegionId: number | null;
  targetRegionId: number | undefined;
  travelSegments: EntityGoal[];
}) {
  const sortedSegs = useMemo(
    () => sortTravelSegments(travelSegments.filter((g) => g.goal_type === "travel_segment")),
    [travelSegments],
  );
  const lineFromChildren = useMemo(() => stopLineFromSegmentGoals(sortedSegs), [sortedSegs]);

  const [preview, setPreview] = useState<TravelRouteApi | null>(null);
  const [loading, setLoading] = useState(false);
  const [fetchErr, setFetchErr] = useState("");

  useEffect(() => {
    if (lineFromChildren) {
      setPreview(null);
      setFetchErr("");
      setLoading(false);
      return;
    }
    if (targetRegionId == null) {
      setPreview(null);
      setFetchErr("");
      setLoading(false);
      return;
    }
    if (previewFromRegionId == null) {
      setPreview(null);
      setFetchErr("");
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setFetchErr("");
    apiGet<TravelRouteApi>(
      `/travel-route?from_region_id=${previewFromRegionId}&to_region_id=${targetRegionId}`,
    )
      .then((data) => {
        if (!cancelled) {
          setPreview(data);
          setLoading(false);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setFetchErr(err.message);
          setPreview(null);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [goalId, lineFromChildren, previewFromRegionId, targetRegionId]);

  if (targetRegionId == null) {
    return null;
  }

  if (lineFromChildren) {
    return (
      <div className="muted small travel-route-preview">
        Route: {lineFromChildren}
      </div>
    );
  }

  if (previewFromRegionId == null) {
    return (
      <div className="muted small travel-route-preview">
        Set entity zone to preview route.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="muted small travel-route-preview">
        Loading route…
      </div>
    );
  }

  if (fetchErr) {
    return (
      <div className="muted small travel-route-preview">
        Route preview failed: {fetchErr}
      </div>
    );
  }

  if (!preview) {
    return null;
  }

  if (preview.reason === "same_region") {
    return (
      <div className="muted small travel-route-preview">
        Already in destination region.
      </div>
    );
  }

  if (preview.reason === "no_route") {
    return (
      <div className="muted small travel-route-preview">
        No route in travel graph.
      </div>
    );
  }

  if (preview.stop_names.length > 0) {
    return (
      <div className="muted small travel-route-preview">
        Route: {preview.stop_names.join(" → ")}
      </div>
    );
  }

  return null;
}
