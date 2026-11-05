# Arsitektur WebUI ChemFlow 3.0

## Batas modul

```text
Browser React / TypeScript
  atoms       Button, Badge, Empty, Notice
  molecules   ResourceStrip, BottomNav, WizardSteps
  features    Login, JobComposer, OptionField, ParameterPanel, ExperimentReview,
              LigandBuilder, ReceptorBuilder, InputRequests, RunWorkspace,
              ArtifactBrowser, MoleculeViewer (NGL, dimuat saat dibutuhkan)
  lib         tipe, API + CSRF, state langsung
       | JSON same-origin / unggahan biner / SSE
FastAPI
  security    sesi, login waktu-konstan, rate limit, CSRF, Origin
  schema      argparse -> skema form -> argv tervalidasi
  receptors   pencarian native + workbook native/manual
  ligands     baris ligan bertipe -> workbook CLI tervalidasi
  prompts     validasi jawaban terstruktur
  tools       registri executable server tepercaya
  storage     pembatasan path + pratinjau inert berbatas
  jobs        SQLite -> worker serial -> siklus hidup pohon proses
  updates     status rilis/sumber GitHub ber-cache
  library     PDF/PPT terautentikasi + sitasi bersama
auto_update   rilis resmi bertahap + aktivasi runtime atomik
       | sys.executable -m chemflow, shell=False, stdin=DEVNULL
CLI -> modul Pipeline / GC-MS / interaction / similarity yang sudah ada
```

`chemflow web` mengimpor dependensi opsional hanya saat dipilih. Modul ilmiah
Python tidak bergantung pada React, npm, atau FastAPI. Metadata versi ada di
pyproject dan chemflow.__version__; paket frontend memakai versi rilis yang sama.

Parser CLI adalah sumber nama opsi, tipe, pilihan, grup, nilai bawaan, dan deskripsi
ilmiah. `schema.py` menampilkan argumen ilmiah dan ID executable terdaftar, sementara
path keluaran, progres terminal, dan bypass TLS tetap dikendalikan server. Pemilihan
executable otomatis memakai mekanisme CLI/cache/PATH yang sudah ada. Pilihan tool
eksplisit hanya diselesaikan ke berkas yang ada di PATH atau path yang didaftarkan
lewat variabel lingkungan operator; path sembarang dari browser ditolak. Referensi
input berupa ID berkas yang diunggah atau `run:JOB_ID:RELATIVE_PATH`; path server
sembarang ditolak. Nama keluaran dan sufiks interaksi tidak boleh memuat path.
Server menyuntikkan direktori keluaran terkelola dan verifikasi TLS. Flag untuk
menolak prompt tetap dapat dipilih. Opsi argparse baru umumnya muncul otomatis di
browser; pelihara daftar blokir untuk opsi baru yang membaca/menulis path sembarang
atau menjalankan program.

CLI melakukan validasi ilmiah. Validasi input web mencegah argumen yang cacat atau
tidak aman dan melaporkan kegagalan enqueue di dekat form. Job tetap bisa gagal
karena workbook kehilangan kolom, binary tidak ada, RCSB tidak tersedia, atau
prasyarat ilmiah tidak terpenuhi. Log menampilkan kegagalan tersebut.

## Persistensi dan siklus hidup

`WORKSPACE/jobs.sqlite3` menyimpan job beserta stempel waktu, status, dan argv
terserialisasi. `uploads/ID/FILENAME` menyimpan input yang tidak berubah;
`runs/OUTPUT_ID` memuat semua keluaran/checkpoint ilmiah; `logs/JOB_ID.log`
mencatat tiap pemanggilan. Job resume/similarity/interactions merujuk ID keluaran
sumbernya. Worker serial mencegah penulis bersamaan dan otomasi desktop BIOVIA
yang saling bersaing. `.server.lock` memakai penguncian berkas OS (msvcrt/fcntl)
untuk menolak server kedua pada workspace yang sama. Pemulihan menandai job yang
sebelumnya berjalan sebagai terinterupsi dan memutar ulang job antre. Checkpoint
ilmiah tetap dimiliki RunState.

Pembatalan memakai psutil untuk menghentikan turunan proses anak lalu proses CLI;
sisa proses dimatikan paksa setelah jeda berbatas. Tidak ada string perintah shell
yang dibangun. Shutdown mempertahankan job antre dan menginterupsi job aktif.
Kalkulasi yang dimatikan paksa di tengah jalan dapat meninggalkan artefak parsial;
resume memakai aturan checkpoint asli. Simpan cadangan workspace secara berkala di
luar. Impor CLI menyalin berkas biasa tanpa symlink dan membuat run hasil impor;
folder sumber tidak disentuh.

## Autentikasi dan operasi jarak jauh

Satu kata sandi workspace diatur di server atau dibuat saat startup. Kata sandi
dibandingkan lewat digest SHA-256 berukuran tetap dengan pembandingan waktu-konstan;
tidak ditulis ke SQLite maupun dikirim ke lingkungan proses anak. ID sesi opak acak
dan token CSRF hanya disimpan di memori, dibatasi 64 sesi, dengan kedaluwarsa mutlak
8 jam. Percobaan login dibatasi global 10 per menit. Restart membatalkan semua sesi.
Tidak ada isolasi pengguna/peran: sesi yang berwenang berbagi seluruh workspace.
Pembatasan identitas multipengguna ditempatkan di proxy.

Cookie HttpOnly dan SameSite=Strict melindungi sesi. Mutasi memerlukan token CSRF
sesi dan Origin same-origin bila disertakan. TrustedHost menolak hostname tak
dikenal; tidak ada middleware CORS permisif. Cookie Secure diaktifkan operator pada
penyebaran HTTPS. Penerusan proxy hanya dipercaya dari loopback pada server CLI,
ditambah IP yang dikonfigurasi eksplisit lewat `--trusted-proxy`. Jangan membuka
HTTP polos ke jaringan yang tidak tepercaya.

Rute API termasuk unduhan dan OpenAPI memerlukan autentikasi. Kode SPA statis
bersifat publik dan tidak memuat rahasia. Respons menetapkan nosniff, penolakan
frame, kebijakan referrer, dan CSP. NGL dibundel lokal. HTML yang tidak tepercaya
tidak pernah dirender; teks SVG dan JSON bersifat inert. Hanya gambar raster dan
format molekul dalam daftar izin yang boleh tampil inline; artefak lain berupa
lampiran. Pembatasan Path.resolve berlaku untuk unggahan, artefak, dan berkas
statis, termasuk pelarian lewat symlink. Akses tulis filesystem workspace tetap
menjadi batas kepercayaan tingkat operator.

## State langsung dan pratinjau

`GET /api/events` mengalirkan snapshot SSE tiap dua detik berisi job serta
pembacaan CPU, RAM, dan disk host. Kedaluwarsa cookie menutup aliran dengan event
expired. EventSource tersambung ulang otomatis; klien yang terputus juga polling
tiap lima detik. Log di-polling tiap dua detik dan mengembalikan 64 KiB terakhir.
Daftar artefak di-polling tiap lima detik. Daftar mengembalikan hingga 500 job
terbaru / 5.000 artefak. Status berdasarkan kode keluar proses, tahap berdasarkan
progress.json yang ada. Tidak ada persentase selesai rekaan karena tiap tahap
punya biaya berbeda.

Pratinjau workbook memakai openpyxl read-only dengan data_only, maksimal 201
baris/60 kolom dan 100 MB isi ZIP tak terkompresi. Sel rumus menampilkan nilai
tersimpan, bukan rumus yang dievaluasi ulang. CSV/TSV/teks punya keluaran
berbatas. Berkas pratinjau dibatasi 20 MB; unggahan 100 MB. NGL hanya memuat
berkas struktur terpilih saat dibutuhkan, membuang stage WebGL saat navigasi,
mengamati perubahan ukuran kanvas, dan menyediakan kontrol koordinat/model.
Struktur yang sangat besar sebaiknya dibuka di penampil lokal. Tabel dan gambar
tetap dapat diperiksa meski browser tidak mendukung WebGL.

Pemeriksaan status GitHub memakai URL resmi tetap, timeout, dan cache enam jam.
`chemflow.auto_update.AutoUpdater` memasang rilis stabil dalam venv berversi baru,
menguji impor/versi/frontend terbundel, lalu memperbarui penunjuk runtime secara
atomik. Bootstrap CLI menjalankan ulang runtime itu dengan argumen asli. Watcher
WebUI memegang kunci maintenance job manager hanya saat antrean kosong, menyiapkan
rilis, dan meminta Uvicorn berhenti dengan anggun sebelum meluncurkan ulang dengan
argumen server kanonis. Instalasi gagal melepas maintenance dan mempertahankan
runtime lama. Checkout sumber yang kotor menunda instalasi. Subproses worker
melewati bootstrap. Unduhan dibatasi pada repositori resmi; SHA256 rilis opsional,
batas ukuran/path/symlink arsip, dan kunci antarproses melindungi aktivasi.
Lihat [kebijakan operator](webui.md#pembaruan-otomatis-github) untuk prasyarat/cache.

`BrandMark`, `Select`, `Disclosure`, dan `Button` adalah atom yang dapat dipakai
ulang dengan gaya khusus bersama. Motion menangani transisi rute/langkah/dialog/
popover dan sketsa molekul berputar; preferensi reduced-motion menekan gerak
spasial. NGL mempertahankan kontrol pointer/sentuh miliknya. `lib/gridbox.ts`
membangkitkan delapan sudut pusat±setengah-ukuran dan dua belas tepi untuk kedua
penampil struktur. `GridBoxViewer` memuat blob PDB terautentikasi; pemilihan
native dan props koordinat memperbarui representasi NGL dan bentuk kotak tanpa
mengubah data ilmiah.

`PdfReader` dimuat saat dibutuhkan dengan worker PDF.js, WASM, dan font standar
lokal. Ia mengambil PDF terbundel terautentikasi, merender halaman kanvas dengan
penanganan resize/DPR, dan menyediakan teks hasil ekstraksi bagi teknologi bantu.
PPTX asli tersedia sebagai unduhan terautentikasi. `chemflow.citations` memasok
referensi yang identik untuk API dan CLI; keluaran BibTeX CLI tidak memuat banner
terminal. `ScientificChart` memakai baris pratinjau aktual, kolom numerik
eksplisit, dan plot SVG berhalaman. Ia tidak pernah mengarang nilai numerik yang
hilang. Batas berkas/sheet sumber tetap terlihat, dengan tooltip keyboard dan
unduhan SVG.

## Pengembangan dan pengujian

```sh
python -m pip install -e ".[web,test]"
cd frontend
npm ci
npm run build
npm test
npx playwright install chromium
npm run test:e2e
```

Vite dev memproksi /api ke 127.0.0.1:8000. Gunakan origin browser yang konsisten
selama pengembangan; autentikasi lewat proxy same-origin Vite. Produksi melayani
SPA hasil build dan API pada origin yang sama. `GET /api/openapi.json` tersedia
setelah login bagi pengembang klien. Helper API browser menyimpan CSRF di memori;
bootstrap sesi mendapat salinan baru setelah refresh. Jangan pernah menyimpan kata
sandi di localStorage.

Tambahkan fitur sebagai modul fitur; jaga agar primitif bebas
dari pemanggilan API. Perbarui pengujian untuk perubahan siklus hidup/keamanan
dan gunakan integrasi subproses CLI nyata, bukan hanya mock. CI lintas-OS adalah
pemeriksaan portabilitas; lulus di Windows lokal saja tidak membuktikan perilaku
macOS/Linux.

## Frontend terpandu dan jembatan input runtime

`JobComposer` memegang state draf, validasi langkah, dan pembuatan job.
`WizardSteps` memuat semantik navigasi; `ParameterPanel` menangani kategori/pencarian;
`OptionField` merender opsi bertipe; `ExperimentReview` menampilkan nilai terpilih.
Metadata alur kerja ada di `lib/workflows.ts`. `BottomNav` memiliki dialog native
ponsel dan navigasi lima item. `styles/shell.css` dan `styles/wizard.css` memuat
tata letak workbench dan gaya form; `styles.css` mempertahankan aturan dasar dan
pratinjau ilmiah. State draf memakai sessionStorage, tidak pernah penyimpanan kredensial.

Anak proses CLI ilmiah menerima `CHEMFLOW_PROMPT_DIR=WORKSPACE/prompts/JOB_ID`.
Fungsi prompt terminal standar memeriksa jembatan ini sebelum pemeriksaan TTY;
tanpa variabel lingkungan itu perilaku CLI-nya tidak berubah. Proses anak menulis
permintaan UUID secara atomik, menunggu balasan paling lama 24 jam, lalu
mengonsumsinya. Cara ini menghindari scraping terminal dan penerimaan perintah
stdin sembarang.

`GET /api/jobs/ID/inputs` mendaftar permintaan terstruktur yang tertunda hanya
saat job berjalan. `POST /api/jobs/ID/inputs/PROMPT_ID` mensyaratkan pemeriksaan
sesi, CSRF, dan origin, memvalidasi SMILES dengan RDKit atau XYZ hingga/ukuran
gridbox positif, lalu menulis balasan secara atomik. Kunci manager menjamin satu
jawaban diterima lintas perangkat; pengulangan/job yang sudah berhenti
mengembalikan 409. Anak proses tetap dapat dibatalkan lewat siklus hidup pohon
proses yang ada. Rekaman job SSE memuat `pending_input`; polling form tiap 2 detik.
Resume yang diaktifkan di browser memulihkan pengaturan interaktif bahkan untuk
konfigurasi impor yang sebelumnya menonaktifkan prompt, kecuali opt-out eksplisit dipilih.

`POST /api/ligands` memvalidasi baris bertipe, menulis workbook rapi yang aman
sebagai teks, dan mengembalikan ID unggahan biasa. `GET /api/vina-versions` memakai
manajer rilis Vina yang ada dengan cache satu jam. Tidak ada implementasi ilmiah
baru yang diduplikasi.
