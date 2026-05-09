const API_BASE = "http://localhost:8000";

export async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    let detail = "";
    try {
      const body = await res.json();
      detail = typeof body?.detail === "string" ? `: ${body.detail}` : "";
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(`Request to ${path} failed (${res.status})${detail}`);
  }
  return (await res.json()) as T;
}
