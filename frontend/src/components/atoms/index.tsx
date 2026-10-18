import { motion } from "motion/react";
import type { ButtonHTMLAttributes, ReactNode } from "react";
export function Button({
  children,
  variant = "primary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      className={`button ${variant}`}
      {...(props as any)}
    >
      {children}
    </motion.button>
  );
}
export function Badge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    imported: "Diimpor",
    queued: "Mengantre",
    running: "Berjalan",
    succeeded: "Selesai",
    failed: "Gagal",
    cancelled: "Dibatalkan",
    interrupted: "Terhenti",
  };
  return (
    <span className={`badge ${status}`}>
      <span aria-hidden="true" className="status-dot" />
      {labels[status] || status}
    </span>
  );
}
export function Empty({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="empty">
      <div className="empty-icon" aria-hidden="true">
        {icon}
      </div>
      <h3>{title}</h3>
      <p>{children}</p>
      {action}
    </div>
  );
}
export function Notice({ children }: { children: ReactNode }) {
  return (
    <div className="notice" role="alert">
      {children}
    </div>
  );
}
