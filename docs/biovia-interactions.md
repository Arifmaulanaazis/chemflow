# Ekspor Interaksi Otomatis dari BIOVIA

Analisis similaritas ([similarity-analysis.md](similarity-analysis.md)) membutuhkan diagram
dan tabel interaksi tiap kompleks dari BIOVIA Discovery Studio. `chemflow.interaction`
mengambilnya sendiri: tiap `complexes/<kunci>/<basis>.pdb` dibuka di GUI BIOVIA, interaksi
ligan-reseptornya dihitung BIOVIA, lalu diagram 2D dan tabel Non-bond disimpan. Hasilnya
persis berkas yang dicari `chemflow similarity`, sehingga alur dari docking sampai
similaritas bisa berjalan sekali jalan.

Seluruh perhitungan interaksi tetap dikerjakan BIOVIA. chemflow hanya menekan tombol yang
sama dengan pengguna, tidak menyertakan aplikasi maupun lisensi BIOVIA.

## Persyaratan

- Windows 10 atau 11 dengan sesi desktop yang aktif dan tidak terkunci.
- BIOVIA Discovery Studio (versi Visualizer yang gratis sudah cukup), bahasa antarmuka
  Inggris. Diuji pada Discovery Studio 2021.
- Paket Python `pywinauto`, `pyperclip`, dan `psutil`. Ketiganya ikut terpasang lewat
  `pip install -r requirements.txt` di Windows.

Modul ini aman diimpor di platform lain. Di sana perintah yang membutuhkannya berhenti
dengan pesan jelas, dan `chemflow run` melewati tahap ini sendiri.

## Pemakaian

### Otomatis pada `chemflow run`

Similaritas berjalan **sendiri** bila mesin memenuhi syarat: Windows, paket otomasi terpasang,
BIOVIA terdeteksi, dan ada ligan native sebagai referensi. Tidak perlu opsi apa pun:

```bash
python -m chemflow run --ligands ligan.xlsx --receptors reseptor.xlsx --output hasil/
```

Setelah tahap analitik, chemflow mengekspor interaksi semua kompleks, lalu menghitung
similaritas terhadap ligan native (`similaritas_interaksi.xlsx` dan grafik). Bila salah satu
syarat tidak terpenuhi (mesin bukan Windows, BIOVIA tidak terpasang, atau `--no-native`),
tahap itu dilewati dengan satu baris log yang menyebut penyebabnya, dan run selesai normal.

| Opsi | Efek |
|---|---|
| (tanpa opsi) | Otomatis: jalan bila terdeteksi, dilewati bila tidak. |
| `--similarity` | Paksa. Bila BIOVIA tidak tersedia, log mencatat galatnya dan similaritas tetap dihitung dari berkas interaksi yang sudah ada. |
| `--no-similarity` | Matikan walau BIOVIA terdeteksi. |

Di library, `PipelineConfig.run_similarity` bernilai `None` (otomatis), `True` (paksa), atau
`False` (matikan), dan `detect_biovia()` mengembalikan jalur executable bila otomasi bisa
berjalan di mesin itu. Karena membutuhkan referensi native, `--similarity` tidak bisa
dipadukan dengan `--no-native`.

### Ekspor saja


Pada folder hasil yang sudah ada (mis. docking dijalankan di mesin lain):

```bash
python -m chemflow interactions --output hasil/
python -m chemflow similarity --output hasil/
```

| Opsi | Bawaan | Kegunaan |
|---|---|---|
| `--output` | wajib | Folder output `chemflow run` yang berisi `complexes/` |
| `--interactions-dir` | `<output>/interaksi` | Folder hasil ekspor |
| `--interaction-suffix` | `_interaksi.xlsx` | Akhiran nama Excel; samakan dengan `chemflow similarity` |
| `--receptor` | semua | Hanya satu reseptor (nama folder, mis. `1UWH_R001`) |
| `--force` | mati | Ekspor ulang walau hasilnya sudah lengkap |
| `--biovia-exe` | deteksi otomatis | Jalur `DiscoveryStudio<tahun>.exe` |
| `--biovia-timeout` | `90` | Batas menunggu jendela BIOVIA muncul (detik) |
| `--no-lock-input` | mati | Jangan kunci mouse dan keyboard selama ekspor |

Pada `chemflow run`, opsi yang tersedia adalah `--similarity` / `--no-similarity`, `--biovia-exe`,
`--biovia-timeout`, dan `--no-lock-input`. `chemflow resume` menerima `--biovia-exe` bila lokasi
BIOVIA berubah.

### Mouse dan keyboard dikunci selama ekspor

BIOVIA dikendalikan lewat input yang sama dengan pengguna, jadi satu klik atau ketikan yang
salah bisa mengubah hasil. Karena itu chemflow **mengunci mouse dan keyboard** selama ekspor
(bawaan, tanpa hak administrator). Pemasangannya lewat hook tingkat rendah Windows
(`WH_KEYBOARD_LL` dan `WH_MOUSE_LL`) yang membuang setiap peristiwa dengan flag *injected*
tidak ada, yaitu input fisik dari perangkat Anda. Input yang dikirim otomasi berflag
*injected* sehingga tetap lewat. Kunci hanya berlaku selama blok ekspor dan selalu dilepas
sesudahnya, juga saat ekspor gagal.

Pengaman supaya komputer tidak terkunci:

- **Esc tiga kali berturut-turut** (dalam 2 detik) membatalkan ekspor. Otomasi berhenti dengan
  rapi pada langkah berikutnya, kunci dilepas, dan `chemflow run` mencetak perintah `resume`.
- Kunci dilepas otomatis bila otomasi tidak bergerak lebih dari 120 detik (detak dikirim tiap
  langkah otomasi).
- Ctrl+Alt+Del tidak bisa dicegat oleh hook, dan hook lenyap bersama prosesnya bila chemflow
  ditutup paksa.
- Bila hook gagal dipasang, chemflow memberi peringatan dan tetap jalan; jangan menyentuh mouse
  atau keyboard dalam kasus itu.

`--no-lock-input` mematikan penguncian. Di Linux dan macOS penguncian tidak aktif (dan ekspor
BIOVIA memang tidak tersedia). Sebelum tiap tombol atau klik dikirim, chemflow tetap memeriksa
bahwa jendela aktif milik BIOVIA; bila fokus berpindah, kompleks itu dicatat gagal dan input
tidak dikirim ke aplikasi lain. Sekitar 20 detik per kompleks, jadi run dengan ratusan kompleks
(`--merge-mode all`) memakan waktu lama; `--receptor` membantu membaginya.

## Deteksi instalasi

Tanpa `--biovia-exe`, chemflow mencari `DiscoveryStudio<tahun>.exe` dari:

1. Kunci registry `App Paths` (HKLM 64-bit dan 32-bit, lalu HKCU).
2. Folder `BIOVIA\Discovery Studio <tahun>\bin` di Program Files (64-bit dan 32-bit).

Instalasi dengan tahun terbesar dipilih (2025 mengalahkan 2021). Folder yang tidak punya
`bin` dan executable, misalnya sisa instalasi yang gagal, tidak dihitung. `--biovia-exe`
boleh berupa berkas `.exe`, folder `bin`, atau folder instalasi. Bila BIOVIA sudah berjalan,
instance itu dipakai; bila chemflow yang membukanya, BIOVIA ditutup lagi setelah selesai.

```python
from chemflow import BioviaLocator

locator = BioviaLocator()
for install in locator.installations():      # tahun terbaru lebih dulu
    print(install.year, install.executable)
```

## Galat lisensi saat BIOVIA dibuka dari Python

Bila BIOVIA berhenti dengan "could not start because there is a licensing problem" padahal
dibuka manual normal, penyebabnya bukan lisensi. Pesan rincinya (tombol More) berbunyi
`Failed to load the module 'ls_license64_vs2017'`. BIOVIA memuat modul lisensi lewat PATH yang
diisi Windows dari nilai `Path` di kunci registry:

```
HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\DiscoveryStudio2021.exe
```

Nilai itu (folder `bin` dan `Common Files\BIOVIA\LicensePack`) hanya ditambahkan bila aplikasi
dibuka lewat shell (klik ganda, `os.startfile`). `subprocess.Popen` biasa tidak membawanya.
chemflow menambahkan direktori itu ke PATH proses BIOVIA yang diluncurkan
(`BioviaLocator.launch_environment`), jadi galat ini tidak muncul. Galat lisensi yang
tersisa berarti lisensinya memang bermasalah dan dilaporkan sebagai `BioviaLicenseError`
beserta teks rinci dari BIOVIA. Periksa lewat Start Menu, BIOVIA, Licensing.

## Yang dikerjakan per kompleks

1. Buka PDB lewat dialog Open (Ctrl+O), tunggu tab dokumennya muncul. BIOVIA membuka salinan
   sementara bernama `<basis>_cf<kode>`. BIOVIA menamai dokumen senama dengan akhiran `(1)`,
   sehingga tanpa nama unik tab chemflow bisa tertukar dengan dokumen milik pengguna.
2. Aktifkan panel Receptor-Ligand Interactions dan pilih ligan menurut rantai dan nama residu
   di sidecar `<basis>.json` (mis. rantai `X`, residu `CUR`). Ion logam pada reseptor bukan
   ligan bagi BIOVIA, jadi tidak mengganggu.
3. Nyalakan Ligand Interactions (BIOVIA menghitung interaksi) lalu Show 2D Diagram, dan
   simpan tangkapan panel diagram beserta legendanya sebagai PNG. PNG diambil sebelum tabel
   dipilih, karena memilih baris tabel mewarnai ulang garis interaksi pada diagram.
4. Buka panel hasil, pilih tab Non-bond, pilih semua baris, salin, dan tulis ke Excel.
   Isi clipboard pengguna dikembalikan sesudahnya.
5. Tutup diagram dan dokumen tanpa menyimpan, lalu hapus salinan sementaranya. Hanya tab yang
   dibuka chemflow yang ditutup; dokumen milik pengguna di BIOVIA tidak disentuh.

Kontrol dicari lewat pohon UI (nama, tipe, dan kelas), bukan koordinat layar, sehingga tidak
bergantung pada resolusi, DPI, atau posisi jendela. BIOVIA dimaksimalkan di awal agar panel
cukup lebar.

## Berkas hasil

```
hasil/interaksi/<kunci>/
    <basis>_interaksi.png       diagram 2D interaksi (panel diagram dan legenda)
    <basis>_interaksi.xlsx      tabel Non-bond, satu sheet "Non-bond"
```

Judul kolom Excel diambil dari tabel BIOVIA. Bawaan Discovery Studio 2021: Name, Visible,
Color, Parent, Distance, Category, Types, From, From Chemistry, To, To Chemistry, Angle XDA,
Angle DAY, Angle DHA, Angle HAY, Angle Deviation, Theta. Jarak dan sudut disimpan sebagai
angka, sisanya teks. BIOVIA tidak menampilkan tab Non-bond bila kompleks tidak punya interaksi;
kompleks itu tetap menghasilkan PNG dan Excel berisi judul saja (dengan peringatan di log).
Pembaca similaritas mencari kolom lewat namanya, jadi menyembunyikan atau mengurutkan ulang
kolom di BIOVIA tidak masalah.

Hasil ditulis ke folder sementara di dalam folder tujuan lalu dipindahkan hanya bila PNG dan
Excel keduanya utuh. Kompleks yang keduanya sudah ada dan tidak kosong dilewati pada
pemanggilan berikutnya, jadi ekspor yang terhenti (Ctrl+C, komputer mati) cukup dijalankan
lagi. Kegagalan satu kompleks dicatat dan tidak menghentikan yang lain; `chemflow interactions`
mengembalikan kode keluar 1 bila ada yang gagal.

## Pemecahan masalah

| Gejala | Penyebab dan solusi |
|---|---|
| `BIOVIA Discovery Studio tidak ditemukan` | Pasang BIOVIA, atau berikan `--biovia-exe`. |
| `Dependensi otomasi Windows belum lengkap` | `pip install pywinauto pyperclip psutil`. |
| `Fokus jendela BIOVIA hilang` | Jendela lain merebut fokus (mis. notifikasi), atau penguncian input dimatikan dan mouse atau keyboard dipakai. Jalankan ulang; yang selesai dilewati. |
| `Dibatalkan pengguna (Esc tiga kali)` | Anda menekan Esc tiga kali. Jalankan ulang perintah yang sama untuk melanjutkan. |
| `Mouse dan keyboard tidak bisa dikunci` | Hook input gagal dipasang. Ekspor tetap jalan; jangan menyentuh mouse dan keyboard sampai selesai. |
| `Ligan X:CUR tidak ada di daftar ligan BIOVIA` | Rantai atau residu di sidecar `.json` tidak cocok dengan isi PDB. Buka PDB-nya di BIOVIA dan periksa "Define Ligand". |
| Peringatan `BIOVIA tidak menampilkan tab Non-bond` | Kompleks itu tidak punya interaksi, atau ligan yang terpilih di BIOVIA bukan ligan hasil docking. Buka PDB-nya di BIOVIA dan periksa. Excel berisi judul saja. |
| `Tangkapan diagram 2D kosong` | Jendela BIOVIA tertutup atau terminimalkan saat pengambilan gambar. |
| `Waktu habis menunggu` | PDB besar atau komputer lambat. Naikkan `--biovia-timeout` atau jalankan per `--receptor`. |
| Similaritas `Format spek atom BIOVIA tidak dikenali` | Berkas interaksi bukan tabel Non-bond BIOVIA yang valid. |

## Pemakaian sebagai library

```python
from chemflow import export_interactions, run_similarity_report

summary = export_interactions("hasil/", receptor="1UWH_R001")     # lock_input=False bila tidak ingin dikunci
print(len(summary.succeeded), len(summary.failed), summary.skipped)
for job, message in summary.failed:
    print(job.receptor_key, job.stem, message)

report = run_similarity_report("hasil/")
print(len(report.results), report.workbook)
```

`export_interactions` melempar `BioviaUnavailableError` (bukan Windows, dependensi kurang,
atau BIOVIA tidak ditemukan), `BioviaLicenseError`, atau `FileNotFoundError` bila `complexes/`
tidak ada. Untuk backend sendiri (pengujian atau alat lain), isi argumen `backend` dengan objek
yang memenuhi `chemflow.interaction.InteractionBackend`; dengan backend sendiri input tidak
dikunci kecuali `lock_input=True`. Kunci input juga bisa dipakai sendiri:

```python
from chemflow.interaction import InputLock

with InputLock(stall_seconds=120) as lock:
    ...                          # panggil lock.pulse() secara berkala; Esc tiga kali melempar InputLockAborted
```

## Keterbatasan

- Hanya Windows, dan hanya satu sesi otomasi pada satu desktop sekaligus: mouse, keyboard,
  clipboard, dan fokus jendela adalah sumber daya bersama. Layar tidak boleh terkunci atau
  sesi remote desktop diputus selama ekspor.
- Diuji pada Discovery Studio 2021 dengan antarmuka berbahasa Inggris. Versi lain bisa
  berbeda pada nama kontrol; galatnya menyebut kontrol yang tidak ditemukan.
- Daftar ligan dicocokkan lewat rantai dan nama residu. Dua ligan pada rantai dan nama yang
  sama tidak dapat dibedakan.
