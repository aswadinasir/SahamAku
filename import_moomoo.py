"""Parser untuk fail CSV eksport sejarah transaksi dari moomoo.

Sokong DUA format CSV moomoo (auto-dikesan daripada header):

1. "History Transactions" (lajur: Symbol, Name, Side, Fill Qty, Fill Price,
   Fill Amount, Fill Time, Markets, Currency, Counterparty) - format ringkas,
   TIADA pecahan caj/komisen (caj diset RM0).

2. "Order History (Cost)" (lajur: Side, Symbol, Name, Order Price, Order Qty,
   Order Amount, Status, Filled@Avg Price, Order Time, Order Type, ...,
   Commission, Platform Fees, Clearing Fee, Stamp Duty, SST, Total) - format
   lengkap dengan caj sebenar (lajur Total). Hanya baris berstatus "Filled"
   diambil; Cancelled/Failed diabaikan.
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


def _parse_history_transactions(reader):
    """Format lama: Fill Qty / Fill Price / Fill Time, tiada caj."""
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
                "komisen": 0.0,
                "yuran_platform": 0.0,
                "yuran_kliring": 0.0,
                "duti_setem": 0.0,
                "sst": 0.0,
                "caj_lain": 0.0,
                "caj": 0.0,
                "nota": f"Import moomoo (kod {simbol})",
                "tarikh_mungkin_tak_tepat": False,
            }
        )

    return hasil


def _angka(teks):
    """Tukar string lajur CSV (boleh kosong/None) kepada float, lalai 0.0."""
    teks = (teks or "").replace(",", "").strip()
    if not teks:
        return 0.0
    try:
        return float(teks)
    except ValueError:
        return 0.0


def _parse_order_history_cost(reader):
    """Format baharu: Status + Filled@Avg Price + Total (caj sebenar).
    Hanya baris Status == "Filled" diambil.
    """
    hasil = []
    dilihat = set()  # (kaunter, order_time_mentah) - elak baris pendua tepat dari CSV

    for baris in reader:
        status = (baris.get("Status") or "").strip().lower()
        if status != "filled":
            continue

        simbol = (baris.get("Symbol") or "").strip()
        nama = (baris.get("Name") or "").strip()
        sisi = (baris.get("Side") or "").strip().lower()
        masa_order = (baris.get("Order Time") or "").strip()
        diisi = (baris.get("Filled@Avg Price") or "").strip()
        jenis_pesanan = (baris.get("Order Type") or "").strip()

        if not simbol or not sisi or not masa_order or "@" not in diisi:
            continue

        kaunter = (nama or simbol).strip().upper()
        kunci_pendua = (kaunter, masa_order)
        if kunci_pendua in dilihat:
            continue
        dilihat.add(kunci_pendua)

        if sisi == "buy":
            jenis = "BELI"
        elif sisi == "sell":
            jenis = "JUAL"
        else:
            continue

        qty_mentah, harga_mentah = diisi.split("@", 1)
        qty_mentah = qty_mentah.replace(",", "").strip()
        harga_mentah = harga_mentah.replace(",", "").strip()

        try:
            tarikh = parse_fill_time(masa_order)
            kuantiti = int(round(float(qty_mentah)))
            harga_seunit = float(harga_mentah)
        except (ValueError, TypeError):
            continue

        if kuantiti <= 0:
            continue

        komisen = _angka(baris.get("Commission"))
        yuran_platform = _angka(baris.get("Platform Fees"))
        yuran_kliring = _angka(baris.get("Clearing Fee"))
        duti_setem = _angka(baris.get("Stamp Duty"))
        sst = _angka(baris.get("SST"))
        jumlah_caj = _angka(baris.get("Total"))

        # Baki selepas tolak 5 fee yang diketahui - serap sebarang fee lain
        # yang mungkin disertakan dalam Total tapi tiada lajur khusus.
        caj_lain = round(jumlah_caj - (komisen + yuran_platform + yuran_kliring + duti_setem + sst), 2)
        if abs(caj_lain) < 0.005:
            caj_lain = 0.0

        hasil.append(
            {
                "tarikh": tarikh,
                "kaunter": kaunter,
                "jenis": jenis,
                "kuantiti": kuantiti,
                "harga_seunit": harga_seunit,
                "komisen": round(komisen, 2),
                "yuran_platform": round(yuran_platform, 2),
                "yuran_kliring": round(yuran_kliring, 2),
                "duti_setem": round(duti_setem, 2),
                "sst": round(sst, 2),
                "caj_lain": caj_lain,
                "caj": round(jumlah_caj, 2),
                "nota": f"Import moomoo (kod {simbol})",
                # Pesanan Stop/Trigger: "Order Time" ialah masa pesanan DILETAK,
                # bukan masa ia dipenuhi - tarikh di atas mungkin tak tepat.
                # Papar amaran di pratonton supaya pengguna semak/betulkan manual.
                "tarikh_mungkin_tak_tepat": "stop" in jenis_pesanan.lower(),
            }
        )

    return hasil


def parse_moomoo_csv(teks_csv):
    """Terima kandungan fail CSV (str), auto-kesan format (lihat docstring
    modul), dan kembalikan senarai dict transaksi yang sedia untuk dipaparkan
    di pratonton import. Baris yang tidak boleh difahami, atau (untuk format
    Order History) tidak berstatus Filled, diabaikan senyap.
    """
    reader = csv.DictReader(io.StringIO(teks_csv))
    fieldnames = reader.fieldnames or []

    if "Status" in fieldnames and "Filled@Avg Price" in fieldnames:
        hasil = _parse_order_history_cost(reader)
    else:
        hasil = _parse_history_transactions(reader)

    hasil.sort(key=lambda r: (r["tarikh"], r["kaunter"]))
    return hasil
