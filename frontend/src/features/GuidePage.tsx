import { BookOpen } from "../components/atoms/Icons";
export default function GuidePage() {
  return (
    <>
      <div className="page-heading">
        <div>
          <h1>Panduan penggunaan</h1>
          <p>Input, parameter, pemantauan proses, dan hasil.</p>
        </div>
        <BookOpen size={32} aria-hidden="true" />
      </div>
      <div className="guide-grid">
        {[
          [
            "Siapkan input",
            "Ikuti empat langkah eksperimen: alur, bahan, pengaturan, dan tinjau. Unggah workbook atau tulis ligan serta reseptor langsung di browser. Template Excel tetap tersedia.",
          ],
          [
            "Jalankan & pantau",
            "Pilih kategori parameter atau cari nama argumen CLI. Setelah ringkasan diperiksa, jalankan eksperimen. Bila SMILES atau gridbox diperlukan, jawab formulir pada halaman job untuk melanjutkan proses.",
          ],
          [
            "Periksa hasil",
            "Pilih berkas pada halaman eksperimen. Struktur PDB/PDBQT dan kompleks dapat diputar dalam viewer 3D. Periksa koordinat atom, model pose, gridbox, dan perkiraan kontak NGL.",
          ],
          [
            "Tabel & interaksi",
            "Workbook menyediakan pilihan worksheet. Pilih tabel interaksi atau diagram BIOVIA di folder interaksi, hasil similaritas, afinitas, ADMET, atau statistik GC-MS. Preview tabel dibatasi; unduhan memuat seluruh data.",
          ],
          [
            "Lanjutkan perhitungan",
            "Job yang dihentikan tetap menyimpan hasil. Gunakan Lanjutkan checkpoint untuk mengerjakan ulang bagian yang belum selesai. Tinjau log untuk kegagalan setiap pasangan docking.",
          ],
          [
            "Akses dari perangkat lain",
            "Operator menjalankan server pada 0.0.0.0 dan mendaftarkan IP/domain melalui --allowed-host. Gunakan HTTPS dan --secure-cookie untuk akses publik melalui Cloudflare Tunnel. BIOVIA tetap memerlukan desktop Windows aktif.",
          ],
        ].map(([title, body], i) => (
          <section className="panel" key={title}>
            <span className="guide-number">{i + 1}</span>
            <h2>{title}</h2>
            <p>{body}</p>
          </section>
        ))}
      </div>
      <p className="subtle">
        Referensi lengkap tersedia di docs/webui.md dan
        docs/webui-architecture.md pada source code.
      </p>
    </>
  );
}
