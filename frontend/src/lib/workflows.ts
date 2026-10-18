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
  "Apa yang ingin Anda kerjakan?",
  "Siapkan bahan eksperimen.",
  "Sesuaikan perhitungan Anda.",
  "Siap memulai eksperimen?",
];
export const notes = [
  "Pilih satu alur. Kami akan menampilkan input yang relevan.",
  "Unggah workbook atau susun data langsung di browser.",
  "Bawaan CLI sudah terisi sebagai panduan. Ubah hanya yang diperlukan.",
  "Periksa input dan pengaturan sebelum masuk antrean.",
];
