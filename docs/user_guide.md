# Panduan Penggunaan Noteration

**Noteration** adalah aplikasi desktop untuk mengelola catatan literatur secara terintegrasi. Menyatukan editor Markdown,
viewer PDF, manajemen literatur Papis, dan sinkronisasi Git dalam satu antarmuka.

---

## Daftar Isi

1. [Memulai — Vault](#1-memulai--vault)
2. [Antarmuka Utama](#2-antarmuka-utama)
3. [Editor Markdown](#3-editor-markdown)
4. [Wiki-link antar Catatan](#4-wiki-link-antar-catatan)
5. [Sitasi dan Autocomplete @citation](#5-sitasi-dan-autocomplete-citation)
6. [Pencarian Global Vault](#6-pencarian-global-vault)
7. [Viewer PDF dan Anotasi](#7-viewer-pdf-dan-anotasi)
8. [Manajemen Literatur (Papis)](#8-manajemen-literatur-papis)
9. [Backlink Graph](#9-backlink-graph)
10. [Sinkronisasi Git](#10-sinkronisasi-git)
11. [Pengaturan](#11-pengaturan)
12. [Shortcut Lengkap](#12-shortcut-lengkap)
13. [Konfigurasi `config.toml`](#13-konfigurasi-configtoml)
14. [Struktur Vault](#14-struktur-vault)
15. [Pertanyaan Umum (FAQ)](#15-pertanyaan-umum-faq)

---

## 1. Memulai — Vault

Noteration bekerja berbasis **Vault**: sebuah folder yang menjadi pusat semua
catatan, literatur, anotasi, dan lampiran Anda.

### Membuat Vault Baru

1. Jalankan Noteration — dialog **Pilih Vault** muncul otomatis.
2. Klik **Buat Vault Baru**.
3. Isi nama vault dan pilih lokasi folder.
4. Klik **Buat** — folder akan dibuat beserta struktur subfoldernya.

### Membuka Vault yang Ada

1. Di dialog **Pilih Vault**, pilih vault dari daftar riwayat, atau
2. Klik **Buka Folder…** untuk memilih folder vault secara manual.

> **Tips:** Anda dapat membuka beberapa vault sekaligus — setiap vault
> membuka jendela MainWindow tersendiri via **File › Buka Vault…**.

### Menghapus Vault dari Daftar

Klik kanan pada vault di dialog Pilih Vault → **Hapus dari Daftar**.
Ini hanya menghapus entri dari riwayat, bukan menghapus folder-nya.

---

## 2. Antarmuka Utama

```
┌─────────────────────────────────────────────────────────────────┐
│  Toolbar: + Catatan │ Simpan │ Literatur │ Sync │ Cari │ Git: synced   │
├──────────┬──────────────────────────────────────┬───────────────┤
│          │                                      │               │
│Navigator │         Tab utama                    │  Backlinks    │
│          │  (Editor / PDF / Literatur / Sync)   │  ──────────   │
│ ▾ NOTES  │                                      │  Graph        │
│  index   │                                      │               │
│  riset   │                                      │               │
│          │                                      │               │
│ ▾ OUTLINE│                                      │               │
│  # Bab 1 │                                      │               │
│          │                                      │               │
│ ▾ SITASI │                                      │               │
│  @darwin │                                      │               │
│          │                                      │               │
├──────────┴──────────────────────────────────────┴───────────────┤
│ nama-file.md │ Bln 12, Kol 5 │ 342 kata │ ● synced │ vault-name │
└─────────────────────────────────────────────────────────────────┘
```

### Panel Kiri — Navigator

Panel Navigator berisi empat bagian yang bisa di-collapse/expand:

| Bagian | Isi |
|--------|-----|
| **Notes** | Pohon file/folder catatan Markdown. Mendukung drag-and-drop. |
| **Outline** | Daftar heading (`#`, `##`, `###`) dari catatan yang sedang aktif. Klik untuk melompat. |
| **Sitasi** | Daftar `@citation-key` yang digunakan di catatan aktif. Klik untuk melompat. |
| **PDF Terkait** | PDF dari library Papis yang disitasi di catatan aktif. Klik untuk membuka. |

### Menu Bar

| Menu | Isi |
|------|-----|
| **File** | Catatan Baru, Buka Vault, Simpan, Keluar |
| **View** | Toggle sidebar/right panel, Literatur, Sinkronisasi |
| **Cari** | Pencarian global vault (Ctrl+F) |
| **Tools** | Sinkronisasi, Export BibTeX, Bangun Graf Backlink, Pengaturan |
| **Help** | Panduan |

### Panel Kanan — Link Graph

Berisi dua tab:

- **Backlinks**: daftar catatan lain yang menautkan ke catatan yang sedang dibuka.
- **Graph**: visualisasi jaringan wiki-link seluruh vault (lihat [§10](#10-backlink-graph)).

### Status Bar

| Indikator | Keterangan |
|-----------|-----------|
| Nama file | Catatan yang sedang aktif. Tanda `*` berarti ada perubahan belum tersimpan. |
| `Bln X, Kol Y` | Posisi kursor (baris dan kolom). |
| `N kata` | Jumlah kata di catatan aktif (menghilangkan front-matter dan kode). |
| `● synced` / `● modified` / `○ offline` | Status repositori Git. |
| Nama vault | Vault yang sedang terbuka. |

---

## 3. Editor Markdown

### Membuat Catatan Baru

- **Ctrl+N** atau toolbar **+ Catatan** → dialog nama dan folder muncul.
- Isi nama file (tanpa `.md`) dan pilih subfolder jika diinginkan.
- Klik **Buat** — file langsung terbuka di editor.

### Menyimpan

- **Ctrl+S** untuk simpan manual.
- Autosave berjalan otomatis setiap 30 detik (dapat diubah di Pengaturan).
- Saat menutup tab yang belum tersimpan, file tersimpan otomatis.

### Mode Edit vs Mode View (Preview)

Setiap tab editor memiliki dua mode:

| Mode | Tampilan | Cara Beralih |
|------|----------|--------------|
| **Edit** | Teks Markdown mentah dengan syntax highlighting | Tombol `Edit` di toolbar tab |
| **View** | Render HTML dari Markdown | Tombol `View` di toolbar tab, atau `Ctrl+Shift+V` |

> Mode View membutuhkan library `markdown` (opsional). Jika tidak terinstall,
> View menampilkan teks plain.

### Sintaks Markdown yang Didukung

```markdown
# Heading 1
## Heading 2
### Heading 3

**tebal**   _miring_   ~~coret~~   `kode inline`

- item daftar
1. daftar bernomor

> kutipan (blockquote)

```python
# blok kode dengan syntax highlighting
def halo():
    print("Noteration!")
```

![Gambar](attachments/gambar.png)
[Tautan eksternal](https://example.com)
```

### Menempel dan Menyisipkan Gambar

- **Drag & drop** file gambar dari file manager ke editor → gambar disalin
  otomatis ke `attachments/` dan sintaks `![]()` disisipkan.
- **Paste** gambar dari clipboard (Ctrl+V setelah screenshot) → sama seperti drag & drop.

### Nomor Baris dan Highlight Baris Aktif

Nomor baris ditampilkan di sisi kiri editor. Baris yang sedang aktif
disorot dengan warna berbeda. Keduanya dapat dinonaktifkan di **Pengaturan › Editor**.

---

## 4. Wiki-link antar Catatan

Wiki-link adalah cara menghubungkan catatan satu dengan lainnya, mirip seperti Obsidian atau Roam.

### Sintaks

```markdown
Lihat [[nama-catatan]] untuk detail lebih lanjut.
Atau dengan alias: [[nama-catatan|teks yang ditampilkan]]
```

### Navigasi

- **Ctrl+Klik** pada `[[nama-catatan]]` di editor → membuka catatan tersebut.
- Jika catatan belum ada, dialog muncul menawarkan untuk **membuat catatan baru**.
- Klik pada backlink di panel kanan → membuka catatan sumber.

### Resolusi Link

Noteration mencari file `nama-catatan.md` di dalam folder `notes/` secara
rekursif. Nama tidak case-sensitive dan mengabaikan ekstensi `.md`.

### Drag-and-Drop di Navigator

File dan folder catatan dapat dipindahkan dengan cara drag-and-drop di panel Navigator:

- Seret file ke folder tujuan untuk memindahkan.
- Seret ke area kosong untuk memindahkan ke root `notes/`.
- Jika nama sudah ada di tujuan, dialog konfirmasi muncul.
- Tab yang sedang terbuka diperbarui otomatis mengikuti path baru.

---

## 5. Sitasi dan Autocomplete @citation

### Cara Menyisipkan Sitasi

Di dalam editor, ketik `@` diikuti beberapa huruf dari judul, penulis, atau
kunci sitasi:

```markdown
Seperti yang dijelaskan oleh @darwin1859 dalam teori evolusinya...
```

Daftar saran muncul otomatis — pilih dengan tombol panah dan `Enter`.

### Format Sitasi yang Didukung

| Format | Contoh |
|--------|--------|
| Kunci tunggal | `@darwin1859` |
| Dengan halaman | `@darwin1859[hal. 42]` |
| Beberapa sitasi | `@newton1687; @einstein1905` |

### Melompat ke Sitasi

Di panel Navigator bagian **Sitasi**, klik salah satu `@key` untuk melompat
langsung ke kemunculannya di catatan.

### Export BibTeX

- **Tools › Export BibTeX (semua)** — ekspor seluruh library ke satu file `.bib`.
- **Tools › Export BibTeX (note ini)** — ekspor hanya sitasi yang digunakan di catatan aktif.

---

## 6. Pencarian Global Vault

Buka melalui menu **Cari** di menu bar, atau **Ctrl+F** (berlaku untuk seluruh vault, terlepas dari tab yang aktif).

### Lingkup Pencarian

Pencarian Global menjangkau tiga sumber sekaligus:

| Ikon | Sumber | Yang Dicari |
|------|--------|------------|
| 📄 | **Catatan** | Isi semua file `.md` di folder `notes/` |
| 📚 | **Literatur** | Judul, penulis, abstrak, dan tag dari library Papis |
| 📌 | **Anotasi** | Teks highlight dan catatan yang dibuat di PDF |

### Cara Menggunakan

1. Ketik kata kunci — hasil muncul otomatis setelah jeda singkat.
2. Gunakan filter **Case Sensitive** dan **Regex** untuk menyempurnakan.
3. Klik hasil untuk membuka: catatan terbuka di tab editor, literatur terbuka
   di tab Literatur, anotasi membuka PDF di halaman yang relevan.

### Pre-fill dari Seleksi

Jika ada teks yang diseleksi di editor saat membuka dialog ini, teks tersebut
otomatis menjadi kata kunci awal. Dialog ini berlaku untuk pencarian di seluruh
vault (catatan, literatur, dan anotasi).

---

## 7. Viewer PDF dan Anotasi

### Membuka PDF

- Dari tab **Literatur**: klik tombol PDF pada entri literatur.
- Dari panel **PDF Terkait** di sidebar.
- Drag & drop file PDF ke jendela Noteration.

### Navigasi PDF

| Aksi | Cara |
|------|------|
| Pindah halaman | Tombol panah di toolbar viewer, atau scroll |
| Zoom | Tombol `+` / `-` di toolbar, atau `Ctrl+Scroll` |
| Lompat ke halaman | Ketik nomor halaman di kolom navigasi |

### Highlight dan Anotasi

1. Seleksi teks di halaman PDF dengan mouse.
2. Panel anotasi muncul di sisi kanan dengan pilihan:
   - **Highlight** — sorot teks dengan warna (kuning default, dapat diubah di Pengaturan).
   - **Catatan** — tambahkan catatan teks pada seleksi.
   - **Sisipkan teks ke editor** — sisipkan teks sebagai blockquote di editor catatan yang aktif,
     lengkap dengan `@citation-key` otomatis.
3. Gunakan Image untuk highlight gambar dari pdf. Gambar hasilnya akan disimpan di folder annotations/images dalam vault.

### Penyimpanan Anotasi (Non-Destructive)

Anotasi **tidak mengubah file PDF asli**. Semua anotasi disimpan dalam
format JSON di folder `annotations/` dengan nama mengikuti hash SHA-256 file PDF:

```
annotations/
└── a3f8c2...d1b9.json   ← anotasi untuk satu PDF
```

File JSON ini ikut tersinkronisasi via Git, sehingga anotasi dapat dibagikan
atau disinkronkan antar perangkat.

---

## 8. Manajemen Literatur (Papis)

Tab Literatur menampilkan isi library [Papis](https://papis.io/) Anda.

### Menambah Entri Baru

#### Via DOI

1. Klik **+ Tambah via DOI** di toolbar Literatur.
2. Masukkan DOI (contoh: `10.1038/nature12345`).
3. Metadata diambil otomatis dari CrossRef/DOI.org.
4. Klik **Simpan**.

#### Import File (drag & drop)

Seret file PDF ke tab Literatur — dialog metadata muncul untuk diisi.

### Mencari Literatur

Gunakan kolom pencarian di atas daftar. Format pencarian:

| Contoh | Keterangan |
|--------|-----------|
| `darwin evolusi` | Cari di semua field |
| `title:principia` | Cari hanya di judul |
| `tags:fisika` | Filter berdasarkan tag |
| `year:2023` | Filter berdasarkan tahun |

### Aksi pada Entri Literatur

| Aksi | Cara |
|------|------|
| Buka PDF | Klik ikon dokumen pada entri |
| Buat catatan baru | Tombol **Buat Catatan** — membuat `.md` dengan template lengkap |
| Edit metadata | Klik entri → panel detail di sisi kanan |
| Tambah tag | Di panel detail, klik **+ Tag** |
| Salin BibTeX | Klik kanan entri → **Salin BibTeX** |

### Membuat Catatan dari Literatur

Klik **Buat Catatan** pada entri literatur → file `papis-key.md` dibuat
otomatis di `notes/` dengan template:

```markdown
# Judul Paper

Sumber: @papis-key

## Ringkasan

## Catatan Penting

## Kutipan
```

---

## 9. Backlink Graph

Panel kanan berisi dua tab untuk melihat hubungan antar catatan.

### Tab Backlinks

Menampilkan daftar catatan yang memiliki `[[link]]` ke catatan yang
sedang aktif. Klik salah satu untuk membuka catatan tersebut.

Tombol **Bangun Ulang** memindai ulang seluruh vault untuk memperbarui data backlink.

### Tab Graph (Visualisasi)

Graf interaktif yang menampilkan semua catatan sebagai simpul (node) dan
wiki-link sebagai tepi (edge).

| Warna Node | Keterangan |
|-----------|-----------|
| Biru | Catatan normal |
| Oranye/Merah | Catatan yang sedang dibuka |
| Abu-abu | Catatan yatim (orphan — tidak ada yang menautkan ke sini) |

**Interaksi:**

| Aksi | Hasil |
|------|-------|
| Klik node | Membuka catatan tersebut |
| Scroll | Zoom in/out |
| Drag latar | Pan (geser tampilan) |
| Drag node | Memindahkan posisi node |
| Hover node | Menampilkan nama catatan |

**Tombol kontrol:**

- **Bangun Ulang** — scan ulang semua wiki-link.
- **Reset View** — kembalikan zoom dan posisi ke default.
- **Zoom +/−** — zoom manual.

> **Tools › Bangun Ulang Graf Backlink** untuk memperbarui dari seluruh vault.

---

## 10. Sinkronisasi Git

Noteration dapat menyinkronisasi vault ke repositori Git (misalnya GitHub)
secara otomatis maupun manual.

### Persyaratan

- Git sudah terinstall di sistem.
- Vault sudah diinisialisasi sebagai repositori Git, atau Anda membuat
  repositori baru dari dalam Noteration.

### Setup Pertama Kali

1. Buka tab **Sinkronisasi** (View › Sinkronisasi atau toolbar).
2. Jika vault belum Git repo: klik **Inisialisasi Git**.
3. Klik **Set Remote** dan isi URL repositori GitHub:
   ```
   https://github.com/username/nama-vault.git
   ```
4. Klik **Simpan Remote**.
5. Klik **Sinkronisasi Sekarang** untuk push pertama kali.

### Sinkronisasi Manual

- **Ctrl+Shift+S** atau toolbar **Sync** atau **Tools › Sinkronisasi Sekarang**.
- Log proses tampil di tab Sinkronisasi secara real-time.

### Sinkronisasi Otomatis

Jika `auto_sync = true` di `config.toml`, Noteration sync di background
setiap 5 menit (dapat diubah via `sync_interval`). Proses ini tidak
mengganggu UI — badge status di toolbar diperbarui.

### Indikator Status Git

| Badge | Keterangan |
|-------|-----------|
| `Git: synced` (hijau) | Vault tersinkronisasi dengan remote |
| `Git: modified` (oranye) | Ada perubahan lokal yang belum di-commit |
| `Git: ↑2 ↓1` (biru) | 2 commit lokal belum di-push, 1 commit remote belum di-pull |
| `Git: local only` (abu) | Tidak ada remote yang dikonfigurasi |
| `Git: offline` (abu) | Folder bukan repositori Git |

### Resolusi Konflik

Jika terjadi konflik saat sinkronisasi, dialog **Resolusi Konflik** muncul otomatis:

1. Setiap file konflik ditampilkan dalam tab tersendiri.
2. Panel **kiri** menampilkan versi lokal ("milik saya").
3. Panel **kanan** menampilkan versi remote ("dari remote").
4. Panel **bawah** adalah editor resolusi — dapat diedit bebas.
5. Gunakan tombol:
   - **Ambil semua milik saya** — gunakan versi lokal.
   - **Ambil semua dari remote** — gunakan versi remote.
   - **Gabung keduanya** — gabungkan keduanya sebagai titik awal.
6. Klik **Terapkan Resolusi** untuk menyelesaikan dan melanjutkan push.

### Riwayat Commit

Tab Sinkronisasi menampilkan 20 commit terakhir dengan kolom:
SHA, pesan, penulis, dan waktu.

---

## 11. Pengaturan

Buka via **Tools › Pengaturan** atau `Ctrl+,`.

### Tab Editor

| Pengaturan | Keterangan |
|-----------|-----------|
| **Font** | Jenis huruf editor (default: Consolas) |
| **Ukuran Font** | Ukuran huruf dalam pt (default: 12) |
| **Lebar Tab** | Jumlah spasi per Tab (default: 2) |
| **Nomor Baris** | Tampilkan/sembunyikan nomor baris |
| **Indentasi Otomatis** | Ikuti indentasi baris sebelumnya saat Enter |
| **Simpan Otomatis** | Aktifkan/nonaktifkan autosave |
| **Interval Autosave** | Jeda antar autosave dalam detik |

### Tab PDF

| Pengaturan | Keterangan |
|-----------|-----------|
| **Renderer** | `qtpdf` (bawaan) atau `pymupdf` (perlu `pip install pymupdf`) |
| **Warna Highlight Default** | Warna sorotan saat highlight teks PDF |

### Tab Papis

| Pengaturan | Keterangan |
|-----------|-----------|
| **Path Library** | Folder tempat Papis menyimpan entri literatur |

### Tab Sinkronisasi

| Pengaturan | Keterangan |
|-----------|-----------|
| **Sync Otomatis** | Aktifkan sync background |
| **Interval Sync** | Jeda antar sync otomatis (default: 300 detik) |
| **Remote** | Nama remote Git (default: `origin`) |
| **Branch** | Branch yang disinkronkan (default: `main`) |
| **Strategi** | `rebase` (default), `merge`, atau `stash` |

### Tab Tampilan

| Pengaturan | Keterangan |
|-----------|-----------|
| **Tema** | `light`, `dark`, atau `system` (ikuti tema OS) |

Perubahan tema diterapkan **langsung** (live preview) saat memilih.
Klik **Batal** untuk mengembalikan ke tema sebelumnya.

---

## 12. Shortcut Lengkap

### File & Catatan

| Shortcut | Aksi |
|----------|------|
| `Ctrl+N` | Catatan baru |
| `Ctrl+S` | Simpan catatan |
| `Ctrl+Shift+S` | Sinkronisasi Git sekarang |
| `Ctrl+W` | Tutup tab aktif |
| `Ctrl+Q` | Keluar aplikasi |

### Editor

| Shortcut | Aksi |
|----------|------|
| `Ctrl+F` | Pencarian Global Vault (berlaku untuk seluruh vault) |
| `Ctrl+Shift+V` | Toggle mode Edit ↔ View (preview) |
| `Ctrl+Klik` | Navigasi wiki-link |
| `Tab` | Indentasi |
| `Shift+Tab` | Hapus indentasi |

### Navigasi

| Shortcut | Aksi |
|----------|------|
| `F1` | Buka panduan penggunaan ini |
| `Ctrl+,` | Buka Pengaturan |

### Dialog

| Shortcut | Aksi |
|----------|------|
| `Enter` | Konfirmasi |
| `Esc` | Tutup dialog |

---

## 13. Konfigurasi `config.toml`

File konfigurasi berada di `<vault>/.noteration/config.toml`.
Diedit otomatis via dialog Pengaturan, atau bisa diedit manual dengan teks editor.

```toml
[general]
autosave          = true
autosave_interval = 30           # detik (5–600)

[editor]
tab_width         = 2            # spasi per Tab (1–8)
font_family       = "Consolas"   # nama font monospace
font_size         = 12           # ukuran font dalam pt (8–32)
show_line_numbers = true
auto_indent       = true

[pdf]
renderer               = "qtpdf"     # "qtpdf" atau "pymupdf"
default_highlight_color = "#FFEB3B"  # warna hex

[papis]
library_path = "~/noteration/literature"   # path absolut atau ~

[sync]
auto_sync     = true
sync_interval = 300       # detik (minimum 60 disarankan)
remote        = "origin"
branch        = "main"
strategy      = "rebase"  # "rebase", "merge", atau "stash"

[ui]
theme           = "system"   # "light", "dark", atau "system"
sidebar_visible = true
```

---

## 14. Struktur Vault

```
~/nama-vault/
├── .noteration/
│   ├── config.toml          # Konfigurasi vault ini
│   ├── db.sqlite            # Cache index PDF
│   └── link_graph.json      # Cache graf backlink (digenerate otomatis)
│
├── notes/                   # Semua catatan Markdown
│   ├── index.md             # Catatan utama (konvensi)
│   ├── topik-a.md
│   └── subfolder/
│       └── topik-b.md
│
├── literature/              # Dikelola Papis
│   ├── darwin1859/
│   │   ├── info.yaml        # Metadata entri
│   │   └── darwin1859.pdf   # File PDF (opsional)
│   └── einstein1905/
│       └── info.yaml
│
├── annotations/             # Anotasi PDF (JSON, non-destructive)
│   ├── <hash-sha256>.json
│   └── images/
│
└── attachments/             # Gambar dan lampiran catatan
    ├── 20240101_diagram.png
    └── tabel-data.csv
```

### File yang Disinkronisasi via Git

| Disinkronisasi | Tidak Disinkronisasi |
|---------------|---------------------|
| `notes/**/*.md` | `literature/**/*.pdf` (besar) |
| `annotations/*.json` | `.noteration/db.sqlite` (cache) |
| `attachments/*` | `__pycache__/` |
| `docs/` | `.DS_Store`, `Thumbs.db` |
| `.noteration/config.toml` | |

---

## 15. Pertanyaan Umum (FAQ)

**Q: Apakah saya harus menggunakan Papis?**
A: Tidak. Noteration dapat digunakan sebagai editor Markdown + Git sync tanpa
Papis. Fitur sitasi, autocomplete `@`, dan tab Literatur tidak akan tersedia,
tetapi editor, wiki-link, backlink graph, dan sinkronisasi tetap berfungsi penuh.

**Q: Apakah ada biaya untuk menggunakan Noteration?**
A: Tidak. Noteration adalah perangkat lunak open-source di bawah lisensi MIT,
gratis selamanya.

**Q: Bisakah saya menggunakan vault yang sudah ada dari Obsidian?**
A: Ya. Arahkan Noteration ke folder vault Obsidian. Wiki-link `[[...]]` dan
file `.md` sepenuhnya kompatibel. Anotasi PDF Noteration menggunakan format
JSON terpisah, jadi tidak konflik dengan plugin Obsidian.

**Q: PyMuPDF vs QtPDF — mana yang sebaiknya saya gunakan?**
A: Gunakan **PyMuPDF** (`pip install pymupdf`) jika Anda perlu highlight dan
ekstraksi teks yang akurat — kualitas rendernya lebih baik dan mendukung
pencarian teks dalam PDF. Gunakan **QtPDF** jika tidak ingin menginstall
dependensi tambahan; sudah tersedia bawaan bersama PySide6.

**Q: Anotasi saya hilang setelah memindahkan file PDF.**
A: Anotasi disimpan berdasarkan hash SHA-256 konten PDF, bukan berdasarkan
path file. Jika isi PDF tidak berubah, anotasi tetap dapat ditemukan
meskipun path berubah.

**Q: Sync otomatis gagal tanpa notifikasi.**
A: Sync otomatis di background bersifat _silent_ (tidak menampilkan pesan
error). Buka tab **Sinkronisasi** untuk melihat log error secara detail,
atau jalankan sync manual dengan **Ctrl+Shift+S**.

**Q: Bagaimana cara backup vault saya?**
A: Cara termudah adalah dengan Git — push ke GitHub menjadikan GitHub sebagai
backup otomatis. Sebagai alternatif, salin seluruh folder vault ke lokasi
lain. Pastikan menyertakan subfolder `.noteration/` karena di sana tersimpan
`config.toml` dan `link_graph.json`.

**Q: Bisakah saya membuka Noteration di beberapa perangkat?**
A: Ya, dengan Git sync. Push dari perangkat A, pull dari perangkat B.
Jika dua perangkat mengedit file yang sama secara bersamaan, dialog
Resolusi Konflik akan membantu menggabungkan perubahan.

---

*Panduan ini digunakan untuk Noteration v1.0.0*
