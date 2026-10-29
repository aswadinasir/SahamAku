# SahamAku

Sistem rekod jual beli saham ringkas untuk kegunaan sendiri. Rekod transaksi beli/jual,
kos/caj, dan sistem akan kira secara automatik:

- Baki unit saham yang ada bagi setiap kaunter
- Kos purata wajaran (weighted average cost) setiap kaunter
- Untung/rugi direalisasi bagi setiap jualan dan jumlah keseluruhan

## Cara Jalankan

```bash
pip install -r requirements.txt
python app.py
```

Kemudian buka `http://127.0.0.1:5000` di browser.

Data disimpan dalam fail `sahamaku.db` (SQLite) di direktori projek — fail ini tidak
disertakan dalam git (lihat `.gitignore`), jadi backup fail ini secara berkala jika perlu.

## Kaedah Pengiraan

Setiap kaunter dikira menggunakan kaedah **kos purata wajaran**:

- **BELI**: kuantiti dan jumlah kos (harga × kuantiti + caj) ditambah kepada baki kaunter.
- **JUAL**: untung/rugi = (harga jual × kuantiti − caj) − (kos purata semasa × kuantiti jual).
  Baki dan jumlah kos dikurangkan secara berkadar supaya kos purata baki tidak berubah.

Pengiraan ini dilakukan semula setiap kali halaman dimuatkan berdasarkan semua transaksi
tersusun mengikut tarikh — jadi mengedit atau memadam transaksi lama akan mengemaskini
semua pengiraan secara automatik.

## Struktur

- `app.py` — Flask routes (dashboard, transaksi, laporan)
- `portfolio.py` — logik pengiraan baki & untung/rugi
- `schema.sql` — struktur database SQLite
- `templates/`, `static/` — UI
