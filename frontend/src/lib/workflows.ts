import {
  Atom,
  ChartNoAxesCombined,
  RefreshCw,
  Workflow,
  FlaskConical,
  Table2,
} from "../components/atoms/Icons";
export const workflows = [
  {
    id: "run",
    name: "Screening molekuler",
    detail: "Preparasi, docking, interaksi, dan kemometrik.",
    icon: Atom,
  },
  {
    id: "gcms",
    name: "Analisis GC-MS",
    detail: "Kromatogram, pencocokan pustaka, dan statistik.",
    icon: ChartNoAxesCombined,
  },
  {
    id: "resume",
    name: "Lanjutkan run",
    detail: "Lanjut dari checkpoint terakhir yang tersimpan.",
    icon: RefreshCw,
  },
  {
    id: "similarity",
    name: "Similaritas interaksi",
    detail: "Bandingkan interaksi docking dengan ligan native.",
    icon: Workflow,
  },
  {
    id: "interactions",
    name: "Ekspor interaksi BIOVIA",
    detail: "Diagram dan tabel interaksi melalui desktop Windows.",
    icon: FlaskConical,
  },
  {
    id: "init",
    name: "Template input",
    detail: "Buat contoh workbook untuk ligan dan reseptor.",
    icon: Table2,
  },
];
export const stepNames = [
  "Alur kerja",
  "Bahan eksperimen",
  "Pengaturan",
  "Tinjau & jalankan",
];
export const copy = [
  "Pilih alur kerja",
  "Siapkan bahan eksperimen.",
  "Sesuaikan perhitungan Anda.",
  "Tinjau eksperimen",
];
export const notes = [
  "Pilih jenis perhitungan.",
  "Unggah workbook atau susun data langsung di browser.",
  "Nilai kosong menggunakan pengaturan bawaan.",
  "Periksa input dan pengaturan sebelum masuk antrean.",
];
