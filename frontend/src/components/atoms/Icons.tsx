/** Set ikon lokal 24px. Stroke dan viewBox yang sama menjaga kontrol atomik tetap konsisten. */
import type { SVGProps } from "react";
type Props = SVGProps<SVGSVGElement> & { size?: number };
const paths: Record<string, string> = {
  Activity: "M3 12h4l3-8 4 16 3-8h4",
  Atom: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6 M3 5c4-4 22 10 18 14S-1 9 3 5 M21 5c-4-4-22 10-18 14S25 9 21 5",
  BookOpen:
    "M12 5v16 M12 5C8 2 4 3 2 4v15c4-1 7-1 10 2 3-3 6-3 10-2V4c-3-1-6-2-10 1",
  ChevronRight: "m9 5 7 7-7 7",
  FlaskConical: "M9 3h6 M10 3v7L4 20q-1 2 2 2h12q3 0 2-2l-6-10V3 M7 15h10",
  LayoutDashboard: "M3 3h7v8H3z M14 3h7v5h-7z M3 15h7v6H3z M14 12h7v9h-7z",
  LogOut: "M10 4H4v16h6 M9 12h12 m-5-5 5 5-5 5",
  Plus: "M12 4v16 M4 12h16",
  Search: "M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14 M15 15l6 6",
  Settings:
    "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8 M9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1z",
  ShieldCheck: "M12 2 3 6v6q0 6 9 10 9-4 9-10V6z m-5 10 3 3 7-7",
  Terminal: "m5 6 5 5-5 5 M13 17h6",
  Workflow: "M3 3h6v6H3z M15 15h6v6h-6z M6 9v9h9 M9 6h9v9",
  Cpu: "M6 6h12v12H6z M9 1v5 m6-5v5 M9 18v5 m6-5v5 M1 9h5 m-5 6h5 M18 9h5 m-5 6h5 M10 10h4v4h-4z",
  MemoryStick:
    "M3 5h18v12H3z M6 17v4 m4-4v4 m4-4v4 m4-4v4 M6 9h4v4H6z m8 0h4v4h-4z",
  HardDrive: "M5 3h14l3 12v6H2v-6z M2 15h20 M6 18h1 m3 0h1",
  UploadCloud:
    "M7 17H5a4 4 0 0 1-1-8 7 7 0 0 1 13-2 5 5 0 0 1 2 10h-2 M12 21V10 m-4 4 4-4 4 4",
  Play: "m7 3 15 9-15 9z",
  RotateCcw: "M3 10a9 9 0 1 1 1 8 M3 3v7h7",
  Scan: "M8 3H3v5 M16 3h5v5 M3 16v5h5 m8 0h5v-5",
  Eye: "M2 12q10-16 20 0-10 16-20 0 M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6",
  MousePointer2: "m4 2 16 11-7 1-3 7z",
  Download: "M12 2v13 m-5-5 5 5 5-5 M3 15v6h18v-6",
  File: "M5 2h9l5 5v15H5z M14 2v6h5",
  FolderOpen: "M2 5h8l3 3h9l-3 13H2z M2 11h18",
  ChartNoAxesCombined: "M3 20V4 M3 20h18 M6 15l4-5 4 3 7-9",
  Table2: "M3 3h18v18H3z M3 9h18 M9 9v12",
  RefreshCw:
    "M3 10a9 9 0 0 1 16-5l2 3 M21 2v6h-6 M21 14A9 9 0 0 1 5 19l-2-3 M3 22v-6h6",
  Square: "M5 4h14v16H5z",
  Clock: "M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20 M12 6v6l4 2",
  ArrowLeft: "M21 12H3 m7-7-7 7 7 7",
  Trash2: "M3 6h18 M8 6V3h8v3 M5 6l1 16h12l1-16 M10 10v8 m4-8v8",
};
const icon = (name: string) =>
  function Icon({ size = 24, ...props }: Props) {
    return (
      <svg
        width={size}
        height={size}
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.65}
        strokeLinecap="round"
        strokeLinejoin="round"
        {...props}
      >
        <path d={paths[name]} />
      </svg>
    );
  };
export const Activity = icon("Activity"),
  Atom = icon("Atom"),
  BookOpen = icon("BookOpen"),
  ChevronRight = icon("ChevronRight"),
  FlaskConical = icon("FlaskConical"),
  LayoutDashboard = icon("LayoutDashboard"),
  LogOut = icon("LogOut"),
  Plus = icon("Plus"),
  Search = icon("Search"),
  Settings = icon("Settings"),
  ShieldCheck = icon("ShieldCheck"),
  Terminal = icon("Terminal"),
  Workflow = icon("Workflow"),
  Cpu = icon("Cpu"),
  MemoryStick = icon("MemoryStick"),
  HardDrive = icon("HardDrive"),
  UploadCloud = icon("UploadCloud"),
  Play = icon("Play"),
  RotateCcw = icon("RotateCcw"),
  Scan = icon("Scan"),
  Eye = icon("Eye"),
  MousePointer2 = icon("MousePointer2"),
  Download = icon("Download"),
  File = icon("File"),
  FolderOpen = icon("FolderOpen"),
  ChartNoAxesCombined = icon("ChartNoAxesCombined"),
  Table2 = icon("Table2"),
  RefreshCw = icon("RefreshCw"),
  Square = icon("Square"),
  Clock = icon("Clock"),
  ArrowLeft = icon("ArrowLeft"),
  Trash2 = icon("Trash2");

export const ArrowRight = icon("ArrowRight");
