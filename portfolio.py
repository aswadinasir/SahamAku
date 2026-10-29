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
