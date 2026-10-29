"""Parser untuk fail CSV eksport "History Transactions" dari moomoo.

Format lajur yang dijangka (header moomoo):
Symbol, Name, Side, Fill Qty, Fill Price, Fill Amount, Fill Time, Markets, Currency, Counterparty
"""

import csv
import io
import re
from datetime import datetime

_POLA_ZON_MASA = re.compile(r"\s+[A-Za-z]{2,5}$")


def parse_fill_time(teks):
    """"Oct 28, 2026 16:12:54 MYT" -> "2026-10-28" (tarikh sahaja)."""
    tanpa_zon = _POLA_ZON_MASA.sub("", teks.strip())
    dt = datetime.strptime(tanpa_zon, "%b %d, %Y %H:%M:%S")
    return dt.date().isoformat()


def parse_moomoo_csv(teks_csv):
    """Terima kandungan fail CSV (str) dan kembalikan senarai dict transaksi
    yang sedia untuk dipaparkan di pratonton import. Baris yang tidak boleh
    difahami (tiada simbol/sisi/masa, atau nilai tidak sah) diabaikan senyap.
    """
    reader = csv.DictReader(io.StringIO(teks_csv))
    hasil = []
    dilihat = set()  # (kaunter, fill_time_mentah) - elak baris pendua tepat dari CSV

    for baris in reader:
        simbol = (baris.get("Symbol") or "").strip()
        nama = (baris.get("Name") or "").strip()
        sisi = (baris.get("Side") or "").strip().lower()
        qty_mentah = (baris.get("Fill Qty") or "").replace(",", "").strip()
        harga_mentah = (baris.get("Fill Price") or "").replace(",", "").strip()
        masa_isi = (baris.get("Fill Time") or "").strip()

        if not simbol or not sisi or not masa_isi:
            continue

        kaunter = (nama or simbol).strip().upper()
        kunci_pendua = (kaunter, masa_isi)
        if kunci_pendua in dilihat:
            continue
        dilihat.add(kunci_pendua)

        if sisi == "buy":
            jenis = "BELI"
        elif sisi == "sell":
            jenis = "JUAL"
        else:
            continue

        try:
            tarikh = parse_fill_time(masa_isi)
            kuantiti = int(round(float(qty_mentah)))
            harga_seunit = float(harga_mentah)
        except (ValueError, TypeError):
            continue

        hasil.append(
            {
                "tarikh": tarikh,
                "kaunter": kaunter,
                "jenis": jenis,
                "kuantiti": kuantiti,
                "harga_seunit": harga_seunit,
                "caj": 0.0,
                "nota": f"Import moomoo (kod {simbol})",
            }
        )

    hasil.sort(key=lambda r: (r["tarikh"], r["kaunter"]))
    return hasil
