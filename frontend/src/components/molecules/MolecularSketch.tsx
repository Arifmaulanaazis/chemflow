import { useEffect, useId, useRef, useState } from "react";

export default function MolecularSketch({ variant = "hero" }: { variant?: "hero" | "login" }) {
  const host = useRef<HTMLDivElement>(null);
  const hint = useId();
  const [status, setStatus] = useState("loading");
  useEffect(() => {
    let disposed = false;
    let destroy: (() => void) | undefined;
    import("../../lib/heroMoleculeScene")
      .then(({ createHeroMolecule }) => {
        if (disposed || !host.current) return;
        destroy = createHeroMolecule(host.current, () => setStatus("unavailable"), variant);
        setStatus("ready");
      })
      .catch(() => { if (!disposed) setStatus("unavailable"); });
    return () => { disposed = true; destroy?.(); };
  }, [variant]);
  return (
    <div className={`molecule-animation hero-molecule${variant === "login" ? " login-molecule" : ""}`} data-state={status}>
      <div ref={host} className="hero-molecule-viewport" role="region" tabIndex={0}
        aria-label="Ilustrasi molekul 3D interaktif" aria-describedby={hint} />
      {status !== "ready" && <p className="hero-molecule-status" role="status">
        {status === "loading" ? "Menyiapkan molekul 3D…" : "Pratinjau 3D memerlukan WebGL pada browser ini."}
      </p>}
      <p id={hint} className="sr-only">
        Ilustrasi interaktif. Putar dengan mouse atau sentuhan dan cubit untuk zoom.
        Keyboard: tombol panah untuk memutar, tambah atau kurang untuk zoom, R untuk mengembalikan tampilan.
      </p>
    </div>
  );
}
