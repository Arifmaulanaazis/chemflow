import { useEffect, useState } from "react";
import { api } from "./api";
import type { Job, Resources } from "./types";
export function useLive() {
  const [jobs, setJobs] = useState<Job[]>([]),
    [resources, setResources] = useState<Resources | null>(null),
    [connected, setConnected] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    let mounted = true;
    const refresh = () =>
      Promise.all([api<Job[]>("/jobs"), api<Resources>("/resources")])
        .then(([j, r]) => {
          if (mounted) {
            setJobs(j);
            setResources(r);
            setError("");
          }
        })
        .catch((e) => {
          if (mounted) setError(e.message);
        });
    void refresh();
    const stream = new EventSource("/api/events");
    stream.onopen = () => setConnected(true);
    stream.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setJobs(data.jobs);
        setResources(data.resources);
        setError("");
      } catch {
        setError("Data pemantauan tidak dapat dibaca.");
      }
    };
    stream.onerror = () => setConnected(false);
    stream.addEventListener("expired", () =>
      window.dispatchEvent(new Event("session-expired")),
    );
    const poll = window.setInterval(() => {
      if (stream.readyState !== EventSource.OPEN) void refresh();
    }, 5000);
    return () => {
      mounted = false;
      stream.close();
      clearInterval(poll);
    };
  }, []);
  return { jobs, resources, connected, error };
}
