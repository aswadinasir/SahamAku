"""Logik pengiraan portfolio saham: baki unit, kos purata, dan untung/rugi direalisasikan.

Kaedah kos purata wajaran (weighted average cost) digunakan:
- Setiap BELI menambah kuantiti dan kos tunai kepada kaunter berkaitan.
- Setiap JUAL mengira untung/rugi berdasarkan kos purata semasa sebelum jualan,
  kemudian mengurangkan kuantiti & kos secara berkadar supaya kos purata baki tidak berubah.
"""


def kira_ledger(senarai_transaksi):
    """Terima senarai transaksi (tersusun mengikut tarikh, id) dan kembalikan:
    - ledger: senarai sama dengan maklumat tambahan (kos_purata_sebelum, untung_rugi, baki_selepas, kos_purata_selepas)
    - portfolio: dict {kaunter: {'baki': int, 'kos_purata': float, 'nilai_kos': float}}
    """
    state = {}
    ledger = []

    for t in senarai_transaksi:
        kaunter = t["kaunter"]
        s = state.setdefault(kaunter, {"baki": 0, "jumlah_kos": 0.0})
        kos_purata_sebelum = (s["jumlah_kos"] / s["baki"]) if s["baki"] > 0 else 0.0
        untung_rugi = None

        if t["jenis"] == "BELI":
            kos_masuk = t["kuantiti"] * t["harga_seunit"] + t["caj"]
            s["baki"] += t["kuantiti"]
            s["jumlah_kos"] += kos_masuk
        else:  # JUAL
            hasil_jualan = t["kuantiti"] * t["harga_seunit"] - t["caj"]
            kos_asas = kos_purata_sebelum * t["kuantiti"]
            untung_rugi = hasil_jualan - kos_asas
            s["baki"] -= t["kuantiti"]
            s["jumlah_kos"] -= kos_asas
            if s["baki"] <= 0:
                s["baki"] = 0
                s["jumlah_kos"] = 0.0

        kos_purata_selepas = (s["jumlah_kos"] / s["baki"]) if s["baki"] > 0 else 0.0

        baris = dict(t)
        baris["kos_purata_sebelum"] = round(kos_purata_sebelum, 4)
        baris["untung_rugi"] = round(untung_rugi, 2) if untung_rugi is not None else None
        baris["baki_selepas"] = s["baki"]
        baris["kos_purata_selepas"] = round(kos_purata_selepas, 4)
        ledger.append(baris)

    portfolio = {}
    for kaunter, s in state.items():
        if s["baki"] > 0:
            kos_purata = s["jumlah_kos"] / s["baki"]
            portfolio[kaunter] = {
                "baki": s["baki"],
                "kos_purata": round(kos_purata, 4),
                "nilai_kos": round(s["jumlah_kos"], 2),
            }

    return ledger, portfolio


def kira_tunai(senarai_transaksi, senarai_modal):
    """Kira jumlah modal bersih (masuk - keluar) dan anggaran baki tunai
    (modal bersih ditolak perbelanjaan bersih untuk beli/jual saham).
    """
    jumlah_modal = 0.0
    for m in senarai_modal:
        if m["jenis"] == "MASUK":
            jumlah_modal += m["jumlah"]
        else:
            jumlah_modal -= m["jumlah"]

    perbelanjaan_bersih = 0.0
    for t in senarai_transaksi:
        if t["jenis"] == "BELI":
            perbelanjaan_bersih += t["kuantiti"] * t["harga_seunit"] + t["caj"]
        else:
            perbelanjaan_bersih -= t["kuantiti"] * t["harga_seunit"] - t["caj"]

    baki_tunai = jumlah_modal - perbelanjaan_bersih

    return {
        "jumlah_modal": round(jumlah_modal, 2),
        "perbelanjaan_bersih_saham": round(perbelanjaan_bersih, 2),
        "baki_tunai": round(baki_tunai, 2),
    }


def kira_tunai_gabungan(senarai_transaksi, senarai_modal):
    """Sama seperti kira_tunai(), tapi kira perbelanjaan bersih MERENTASI SEMUA
    pasaran (bukan MY sahaja) - transaksi pasaran asing ditukar ke RM guna
    kadar_tukaran yang direkod pada transaksi itu sendiri. Transaksi pasaran
    asing yang tiada kadar_tukaran DIKECUALIKAN (bilangannya dikira berasingan
    supaya UI boleh beri amaran - baki tunai TIDAK lengkap jika ada yang
    dikecualikan).
    """
    jumlah_modal = 0.0
    for m in senarai_modal:
        if m["jenis"] == "MASUK":
            jumlah_modal += m["jumlah"]
        else:
            jumlah_modal -= m["jumlah"]

    perbelanjaan_bersih_rm = 0.0
    bilangan_tiada_kadar = 0
    for t in senarai_transaksi:
        amaun_asal = t["kuantiti"] * t["harga_seunit"] + (t["caj"] if t["jenis"] == "BELI" else -t["caj"])
        if t["pasaran"] == "MY":
            amaun_rm = amaun_asal
        elif t.get("kadar_tukaran"):
            amaun_rm = amaun_asal * t["kadar_tukaran"]
        else:
            bilangan_tiada_kadar += 1
            continue
        if t["jenis"] == "BELI":
            perbelanjaan_bersih_rm += amaun_rm
        else:
            perbelanjaan_bersih_rm -= amaun_rm

    baki_tunai = jumlah_modal - perbelanjaan_bersih_rm

    return {
        "jumlah_modal": round(jumlah_modal, 2),
        "perbelanjaan_bersih_saham": round(perbelanjaan_bersih_rm, 2),
        "baki_tunai": round(baki_tunai, 2),
        "bilangan_tiada_kadar": bilangan_tiada_kadar,
    }
