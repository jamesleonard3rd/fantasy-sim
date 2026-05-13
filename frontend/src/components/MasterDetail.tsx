import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { apiGet } from "../api";
import { EmptyState, ErrorBox, Loader } from "./common";

type Props<TList, TDetail> = {
  listEndpoint: string;
  detailEndpoint?: (id: number) => string;
  refreshIntervalMs?: number;
  getId: (item: TList) => number;
  getTitle: (item: TList) => string;
  getSubtitle?: (item: TList) => string | undefined;
  getMeta?: (item: TList) => string | undefined;
  searchPlaceholder?: string;
  emptyMessage?: string;
  renderDetail: (detail: TDetail) => ReactNode;
  renderListItem?: (item: TList) => ReactNode;
};

export function MasterDetail<TList, TDetail>({
  listEndpoint,
  detailEndpoint,
  refreshIntervalMs,
  getId,
  getTitle,
  getSubtitle,
  getMeta,
  searchPlaceholder = "Search…",
  emptyMessage = "No results.",
  renderDetail,
  renderListItem,
}: Props<TList, TDetail>) {
  const [items, setItems] = useState<TList[] | null>(null);
  const [listError, setListError] = useState<string>("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<TDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string>("");
  const [query, setQuery] = useState("");

  useEffect(() => {
    let cancelled = false;

    const loadList = (showLoader: boolean) => {
      if (showLoader) setItems(null);
      setListError("");
      apiGet<TList[]>(listEndpoint)
        .then((data) => {
          if (cancelled) return;
          setItems(data);
          setSelectedId((currentId) => {
            if (data.length === 0) return null;
            if (currentId !== null && data.some((item) => getId(item) === currentId)) {
              return currentId;
            }
            return getId(data[0]);
          });
        })
        .catch((err: Error) => {
          if (!cancelled) setListError(err.message);
        });
    };

    loadList(true);
    const intervalId =
      refreshIntervalMs && refreshIntervalMs > 0
        ? window.setInterval(() => loadList(false), refreshIntervalMs)
        : undefined;

    return () => {
      cancelled = true;
      if (intervalId !== undefined) {
        window.clearInterval(intervalId);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [listEndpoint, refreshIntervalMs]);

  useEffect(() => {
    if (selectedId == null || !detailEndpoint) {
      setDetail(null);
      return;
    }
    let cancelled = false;

    const loadDetail = (showLoader: boolean) => {
      if (showLoader) setDetailLoading(true);
      setDetailError("");
      apiGet<TDetail>(detailEndpoint(selectedId))
        .then((data) => {
          if (!cancelled) setDetail(data);
        })
        .catch((err: Error) => {
          if (!cancelled) setDetailError(err.message);
        })
        .finally(() => {
          if (!cancelled && showLoader) setDetailLoading(false);
        });
    };

    loadDetail(true);
    const intervalId =
      refreshIntervalMs && refreshIntervalMs > 0
        ? window.setInterval(() => loadDetail(false), refreshIntervalMs)
        : undefined;

    return () => {
      cancelled = true;
      if (intervalId !== undefined) {
        window.clearInterval(intervalId);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedId, detailEndpoint, refreshIntervalMs]);

  const filtered = useMemo(() => {
    if (!items) return [];
    const q = query.trim().toLowerCase();
    if (!q) return items;
    return items.filter((item) => {
      const title = getTitle(item).toLowerCase();
      const subtitle = getSubtitle?.(item)?.toLowerCase() ?? "";
      const meta = getMeta?.(item)?.toLowerCase() ?? "";
      return title.includes(q) || subtitle.includes(q) || meta.includes(q);
    });
  }, [items, query, getTitle, getSubtitle, getMeta]);

  return (
    <div className="master-detail">
      <div className="master-pane">
        <div className="master-search">
          <input
            type="search"
            placeholder={searchPlaceholder}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <span className="master-count">
            {items ? `${filtered.length} / ${items.length}` : ""}
          </span>
        </div>
        <div className="master-list">
          {listError && <ErrorBox message={listError} />}
          {!listError && items === null && <Loader />}
          {!listError && items && filtered.length === 0 && (
            <EmptyState message={emptyMessage} />
          )}
          {!listError &&
            items &&
            filtered.map((item) => {
              const id = getId(item);
              const isActive = id === selectedId;
              return (
                <button
                  key={id}
                  type="button"
                  className={`master-item ${isActive ? "is-active" : ""}`}
                  onClick={() => setSelectedId(id)}
                >
                  {renderListItem ? (
                    renderListItem(item)
                  ) : (
                    <>
                      <div className="master-item-title">{getTitle(item)}</div>
                      {getSubtitle?.(item) && (
                        <div className="master-item-subtitle">
                          {getSubtitle(item)}
                        </div>
                      )}
                      {getMeta?.(item) && (
                        <div className="master-item-meta">{getMeta(item)}</div>
                      )}
                    </>
                  )}
                </button>
              );
            })}
        </div>
      </div>

      <div className="detail-pane">
        {!detailEndpoint ? (
          <EmptyState message="Select an item to inspect its details." />
        ) : selectedId == null ? (
          <EmptyState message="Nothing to show yet." />
        ) : detailError ? (
          <ErrorBox message={detailError} />
        ) : detailLoading || !detail ? (
          <Loader label="Loading details…" />
        ) : (
          renderDetail(detail)
        )}
      </div>
    </div>
  );
}
