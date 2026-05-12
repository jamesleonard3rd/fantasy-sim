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

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "";
    try {
      const responseBody = await res.json();
      detail = typeof responseBody?.detail === "string" ? `: ${responseBody.detail}` : "";
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(`Request to ${path} failed (${res.status})${detail}`);
  }
  return (await res.json()) as T;
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "PUT",
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    let detail = "";
    try {
      const responseBody = await res.json();
      detail = typeof responseBody?.detail === "string" ? `: ${responseBody.detail}` : "";
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(`Request to ${path} failed (${res.status})${detail}`);
  }
  return (await res.json()) as T;
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  if (!res.ok) {
    let detail = "";
    try {
      const responseBody = await res.json();
      detail = typeof responseBody?.detail === "string" ? `: ${responseBody.detail}` : "";
    } catch {
      // ignore non-JSON error bodies
    }
    throw new Error(`Request to ${path} failed (${res.status})${detail}`);
  }
  return (await res.json()) as T;
}
