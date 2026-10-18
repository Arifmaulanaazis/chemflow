# ChemFlow 3.0.0

ChemFlow kini mendukung CLI, library Python, dan WebUI responsif. Komputasi ilmiah
tetap berjalan lewat pipeline dan perintah CLI yang sudah ada. Rilis ini menaikkan
versi minimum Python ke 3.10 dan menambahkan dependensi opsional `web`; Node.js hanya
diperlukan untuk membangun sumber frontend. psutil kini dipasang di semua sistem operasi.

- React / TypeScript / Vite dengan desain khusus, kontrol semantik, dan modul atomik.
- Autentikasi FastAPI, sesi HttpOnly, CSRF, pemeriksaan Origin/Host, dan unggahan berbatas.
- Antrean job persisten, isolasi proses, log dan tahap nyata, serta batal/lanjut/impor.
- Wizard empat langkah, navbar mengambang untuk ponsel, parameter CLI yang dapat dicari, dan tinjauan akhir.
- Pembuat ligan dan reseptor di browser; pertanyaan native/gridbox dan SMILES saat runtime lewat API.
- Pilihan executable server yang terdaftar dan pencarian versi Vina yang kompatibel.
- Inspeksi struktur, pose, koordinat, kontak, dan gridbox dengan NGL; bundel lokal yang dimuat saat dibutuhkan.
- Fit dan Reset memakai batas seluruh struktur agar pita protein tetap masuk layar setelah diputar.
- Gridbox hasil membaca checkpoint reseptor pada run, termasuk run lanjutan dan kompleks RMSD.
- Unggahan difilter menurut jenis input dan format; nama berulang diringkas dengan pilihan aktif dipertahankan.
- Progress bar pada run serta badge jumlah proses berjalan dan antre di navbar desktop/ponsel.
- Radar ekskresi mendukung dua parameter pada profil ligan dan grup, tanpa mengisi area atau menambah sumbu.
- Teks antarmuka diringkas menjadi petunjuk penggunaan dan status proses.
- Pratinjau sheet/tabel workbook, grafik, diagram, dan teks, serta unduhan penuh terautentikasi.
- Pembacaan CPU, RAM, dan disk dari server komputasi lewat SSE dengan sambung ulang/polling.
- Hanya localhost secara bawaan; host LAN/publik dan tunnel HTTPS harus dikonfigurasi eksplisit.
- Pemasangan otomatis rilis GitHub stabil dalam runtime terisolasi yang terverifikasi;
  restart WebUI hanya saat antrean kosong, cache enam jam, dan perlindungan checkout yang kotor.
- Logo resmi, sketsa molekul berputar yang aman untuk ponsel, dan dukungan reduced-motion.
- Dropdown, kotak centang, disclosure, dan navigasi beranimasi khusus memakai Motion.
- Pembaca PDF workshop terautentikasi, unduhan PPT/PDF, dan sitasi bersama CLI/WebUI.
- Visualisasi NGL langsung untuk reseptor/native/gridbox dan grafik SVG numerik interaktif.
- Matriks CI Windows/macOS/Linux; otomasi BIOVIA tetap mensyaratkan Windows.

Workspace memakai satu kredensial operator untuk semua perangkat, bukan akun
terisolasi per penyewa. Pembaruan otomatis mempertahankan checkout/lingkungan awal
dan mengaktifkan runtime terverifikasi yang terpisah. Perintah CLI yang ada tetap
tersedia. Catatan rilis 2.1.0 dan materi workshop ilmiah dipertahankan, dengan
bagian 3.0 yang baru pada PPT/PDF.

Lihat [penggunaan](webui.md), [arsitektur](webui-architecture.md),
[sistem desain](design/webui.md), dan [bukti pengujian](testing-3.0.0.md).
