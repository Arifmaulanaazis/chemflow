let csrf = "";
let serverVersion = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T>(url: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch("/api" + url, {
    ...init,
    credentials: "same-origin",
    headers: {
      ...(init.body instanceof Blob
        ? {}
        : { "Content-Type": "application/json" }),
      "X-CSRF-Token": csrf,
      ...init.headers,
    },
  });
  const version = response.headers?.get?.("X-ChemFlow-Version");
  if (version) {
    if (serverVersion && serverVersion !== version) {
      window.location.reload();
    }
    serverVersion = version;
  }
  if (!response.ok) {
    let message = `Permintaan gagal (${response.status})`;
    try {
      const body = await response.json();
      message =
        typeof body.detail === "string"
          ? body.detail
          : JSON.stringify(body.detail);
    } catch {}
    if (response.status === 401 && !url.startsWith("/login"))
      window.dispatchEvent(new Event("session-expired"));
    throw new Error(message);
  }
  return response.json();
}
export const fileUrl = (id: string, path: string, download = true) =>
  `/api/jobs/${id}/file?path=${encodeURIComponent(path)}&download=${download}`;
export const bytes = (n: number) =>
  n >= 1024 ** 3
    ? `${(n / 1024 ** 3).toFixed(1)} GB`
    : n >= 1024 ** 2
      ? `${(n / 1024 ** 2).toFixed(1)} MB`
      : n >= 1024
        ? `${(n / 1024).toFixed(1)} KB`
        : `${n} B`;
export const date = (n: number) =>
  new Date(n * 1000).toLocaleString("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
  });
export const active = (j: { status: string }) =>
  ["queued", "running"].includes(j.status);
