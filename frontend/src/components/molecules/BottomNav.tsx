import { animate } from "motion";
import { useRef, useState } from "react";
import {
  LayoutDashboard,
  Workflow,
  Plus,
  Activity,
  Settings,
  BookOpen,
  LogOut,
} from "../atoms/Icons";
import { Button } from "../atoms";
export default function BottomNav({
  route,
  navigate,
  onLogout,
  connected,
}: {
  route: string;
  navigate: (s: string) => void;
  onLogout: () => void;
  connected: boolean;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [open, setOpen] = useState(false);
  const close = async () => {
    if (
      dialog.current &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches === false
    )
      await animate(
        dialog.current,
        { opacity: [1, 0], y: [0, 24] },
        { duration: 0.16 },
      );
    dialog.current?.close();
    setOpen(false);
  };
  const destinations = [
    {
      id: "overview",
      label: "Beranda",
      full: "Beranda ruang kerja",
      icon: LayoutDashboard,
    },
    {
      id: "experiments",
      label: "Eksperimen",
      full: "Eksperimen",
      icon: Workflow,
    },
    { id: "new", label: "Buat", full: "Buat eksperimen", icon: Plus },
    {
      id: "resources",
      label: "Mesin",
      full: "Mesin & sumber daya",
      icon: Activity,
    },
  ];
  return (
    <>
      <nav className="bottom-nav" aria-label="Navigasi mobile">
        {destinations.map((n) => (
          <a
            key={n.id}
            href={`#${n.id}`}
            aria-label={n.full}
            aria-current={
              route === n.id ||
              (n.id === "new" && route.startsWith("new/")) ||
              (n.id === "experiments" && route.startsWith("run/"))
                ? "page"
                : undefined
            }
            className={n.id === "new" ? "bottom-create" : ""}
            onClick={(e) => {
              e.preventDefault();
              navigate(n.id);
            }}
          >
            <span>
              <n.icon size={21} aria-hidden="true" />
            </span>
            <small>{n.label}</small>
          </a>
        ))}
        <button
          type="button"
          aria-haspopup="dialog"
          aria-expanded={open}
          onClick={() => {
            setOpen(true);
            dialog.current?.showModal();
            if (dialog.current)
              void animate(
                dialog.current,
                { opacity: [0, 1], y: [24, 0] },
                {
                  duration: window.matchMedia(
                    "(prefers-reduced-motion: reduce)",
                  ).matches
                    ? 0
                    : 0.2,
                },
              );
          }}
        >
          <span>
            <Settings size={21} aria-hidden="true" />
          </span>
          <small>Lainnya</small>
        </button>
      </nav>
      <dialog
        className="mobile-menu"
        aria-labelledby="mobile-menu-heading"
        ref={dialog}
        onCancel={(e) => {
          e.preventDefault();
          void close();
        }}
        onClose={() => setOpen(false)}
        onClick={(e) => {
          if (e.target === dialog.current) close();
        }}
      >
        <div className="sheet-handle" aria-hidden="true" />
        <div className="section-heading">
          <h2 id="mobile-menu-heading">Ruang kerja Anda</h2>
          <Button variant="ghost" onClick={close}>
            Tutup
          </Button>
        </div>
        <p>
          {connected ? "Pemantauan terhubung" : "Menghubungkan pemantauan…"}
        </p>
        <a
          href="#guide"
          onClick={(e) => {
            e.preventDefault();
            close();
            navigate("guide");
          }}
        >
          <BookOpen size={21} aria-hidden="true" />
          Panduan
        </a>
        <a
          href="#library"
          onClick={(e) => {
            e.preventDefault();
            close();
            navigate("library");
          }}
        >
          <BookOpen size={21} aria-hidden="true" />
          Materi & sitasi
        </a>
        <a
          href="#settings"
          onClick={(e) => {
            e.preventDefault();
            close();
            navigate("settings");
          }}
        >
          <Settings size={21} aria-hidden="true" />
          Akses & pembaruan
        </a>
        <button
          type="button"
          onClick={() => {
            close();
            onLogout();
          }}
        >
          <LogOut size={21} aria-hidden="true" />
          Keluar
        </button>
      </dialog>
    </>
  );
}
