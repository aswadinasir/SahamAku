CREATE TABLE IF NOT EXISTS transaksi (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarikh TEXT NOT NULL,
    masa TEXT NOT NULL DEFAULT '',
    kaunter TEXT NOT NULL,
    jenis TEXT NOT NULL CHECK (jenis IN ('BELI', 'JUAL')),
    kuantiti INTEGER NOT NULL CHECK (kuantiti > 0),
    harga_seunit REAL NOT NULL CHECK (harga_seunit >= 0),
    komisen REAL NOT NULL DEFAULT 0 CHECK (komisen >= 0),
    yuran_platform REAL NOT NULL DEFAULT 0 CHECK (yuran_platform >= 0),
    yuran_kliring REAL NOT NULL DEFAULT 0 CHECK (yuran_kliring >= 0),
    duti_setem REAL NOT NULL DEFAULT 0 CHECK (duti_setem >= 0),
    sst REAL NOT NULL DEFAULT 0 CHECK (sst >= 0),
    caj_lain REAL NOT NULL DEFAULT 0 CHECK (caj_lain >= 0),
    nota TEXT,
    dicipta_pada TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_transaksi_kaunter ON transaksi (kaunter);
CREATE INDEX IF NOT EXISTS idx_transaksi_tarikh ON transaksi (tarikh);

CREATE TABLE IF NOT EXISTS modal (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tarikh TEXT NOT NULL,
    jenis TEXT NOT NULL CHECK (jenis IN ('MASUK', 'KELUAR')),
    jumlah REAL NOT NULL CHECK (jumlah > 0),
    nota TEXT,
    dicipta_pada TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_modal_tarikh ON modal (tarikh);
