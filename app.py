import os
import sqlite3
from datetime import date, timedelta

from flask import Flask, g, redirect, render_template, request, url_for

from import_moomoo import parse_moomoo_csv
from portfolio import kira_ledger, kira_tunai

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "sahamaku.db")
SCHEMA_PATH = os.path.join(BASE_DIR, "schema.sql")

app = Flask(__name__)


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        with open(SCHEMA_PATH, encoding="utf-8") as f:
            db.executescript(f.read())


LAJUR_FEE = ["komisen", "yuran_platform", "yuran_kliring", "duti_setem", "sst", "caj_lain"]


def _borang_fee(form, indeks=None):
    """Baca lajur fee daripada borang (medan biasa atau "medan_{indeks}" utk pratonton import)."""
    hasil = {}
    for lajur in LAJUR_FEE:
        nama_medan = f"{lajur}_{indeks}" if indeks is not None else lajur
        hasil[lajur] = float(form.get(nama_medan) or 0)
    return hasil


def muat_semua_transaksi(db):
    rows = db.execute(
        "SELECT * FROM transaksi ORDER BY tarikh ASC, masa ASC, id ASC"
    ).fetchall()
    hasil = []
    for r in rows:
        t = dict(r)
        t["caj"] = round(sum(t[lajur] for lajur in LAJUR_FEE), 2)
        hasil.append(t)
    return hasil


def julat_bulan_semasa():
    hari_ini = date.today()
    awal = hari_ini.replace(day=1)
    if hari_ini.month == 12:
        akhir = hari_ini.replace(day=31)
    else:
        akhir = hari_ini.replace(month=hari_ini.month + 1, day=1) - timedelta(days=1)
    return awal.isoformat(), akhir.isoformat()


def muat_semua_modal(db):
    rows = db.execute(
        "SELECT * FROM modal ORDER BY tarikh ASC, id ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def simbol_mata_wang(kod):
    return "RM" if kod == "MYR" else (kod or "")


@app.template_filter("fmt_unit")
def fmt_unit(nilai):
    """Format kuantiti unit (boleh pecahan, cth 0.0132 saham serpihan) dengan
    pemisah ribu tapi tanpa sifar berlebihan di belakang titik perpuluhan."""
    teks = f"{float(nilai):,.6f}".rstrip("0").rstrip(".")
    return teks or "0"


def kira_ledger_ikut_pasaran(transaksi):
    """Kira ledger & portfolio BERASINGAN bagi setiap pasaran (MY/US/...) supaya
    kos purata & baki tidak tercampur mata wang, kemudian gabung semula ledger
    untuk paparan senarai. Pulangkan (ledger_gabungan, {pasaran: portfolio}).
    """
    ledger_gabungan = []
    portfolio_ikut_pasaran = {}
    for p in sorted({t["pasaran"] for t in transaksi}):
        tx_p = [t for t in transaksi if t["pasaran"] == p]
        ledger_p, portfolio_p = kira_ledger(tx_p)
        ledger_gabungan.extend(ledger_p)
        portfolio_ikut_pasaran[p] = portfolio_p
    return ledger_gabungan, portfolio_ikut_pasaran


@app.route("/")
def dashboard():
    db = get_db()
    transaksi = muat_semua_transaksi(db)
    modal = muat_semua_modal(db)

    pasaran_data = []
    if transaksi:
        ledger, portfolio_ikut_pasaran = kira_ledger_ikut_pasaran(transaksi)
        for p, portfolio in sorted(portfolio_ikut_pasaran.items()):
            ledger_p = [b for b in ledger if b["pasaran"] == p]
            jumlah_ur_p = sum(b["untung_rugi"] for b in ledger_p if b["untung_rugi"] is not None)
            mata_wang_p = next((t["mata_wang"] for t in transaksi if t["pasaran"] == p), "MYR")
            portfolio_senarai = sorted(
                ({"kaunter": k, **v} for k, v in portfolio.items()),
                key=lambda x: x["kaunter"],
            )
            pasaran_data.append({
                "pasaran": p,
                "simbol": simbol_mata_wang(mata_wang_p),
                "portfolio": portfolio_senarai,
                "jumlah_nilai_kos": round(sum(v["nilai_kos"] for v in portfolio.values()), 2),
                "jumlah_untung_rugi": round(jumlah_ur_p, 2),
                "bilangan_kaunter": len(portfolio),
            })

    # Modal & anggaran baki tunai: direkod dalam RM, jadi hanya pasaran MY diambil kira.
    tx_my = [t for t in transaksi if t["pasaran"] == "MY"]
    tunai = kira_tunai(tx_my, modal)

    return render_template(
        "dashboard.html",
        pasaran_data=pasaran_data,
        jumlah_modal=tunai["jumlah_modal"],
        baki_tunai=tunai["baki_tunai"],
    )


@app.route("/transaksi")
def senarai_transaksi():
    db = get_db()
    transaksi = muat_semua_transaksi(db)
    ledger, _ = kira_ledger_ikut_pasaran(transaksi)
    for b in ledger:
        b["simbol"] = simbol_mata_wang(b["mata_wang"])

    senarai_kaunter = sorted({t["kaunter"] for t in transaksi})

    if "dari" in request.args:
        # Borang tapisan dihantar (termasuk "Kosongkan Tapisan") - guna terus apa yang dihantar.
        f_dari = request.args.get("dari", "").strip()
        f_hingga = request.args.get("hingga", "").strip()
    else:
        # Lawatan pertama / klik nav - lalai tapis kepada bulan semasa.
        f_dari, f_hingga = julat_bulan_semasa()
    f_kaunter = request.args.get("kaunter", "").strip().upper()
    f_pasaran = request.args.get("pasaran", "").strip().upper()

    ledger_tapis = ledger
    if f_dari:
        ledger_tapis = [t for t in ledger_tapis if t["tarikh"] >= f_dari]
    if f_hingga:
        ledger_tapis = [t for t in ledger_tapis if t["tarikh"] <= f_hingga]
    if f_kaunter:
        ledger_tapis = [t for t in ledger_tapis if t["kaunter"] == f_kaunter]
    if f_pasaran:
        ledger_tapis = [t for t in ledger_tapis if t["pasaran"] == f_pasaran]

    ledger_tapis.sort(key=lambda t: (t["tarikh"], t["masa"], t["id"]), reverse=True)
    diimport = request.args.get("diimport", type=int)
    return render_template(
        "transaksi.html",
        ledger=ledger_tapis,
        hari_ini=date.today().isoformat(),
        diimport=diimport,
        senarai_kaunter=senarai_kaunter,
        senarai_pasaran=sorted({t["pasaran"] for t in transaksi}),
        f_dari=f_dari,
        f_hingga=f_hingga,
        f_kaunter=f_kaunter,
        f_pasaran=f_pasaran,
        ada_tapisan=bool(f_dari or f_hingga or f_kaunter or f_pasaran),
    )


PASARAN_MATA_WANG_LALAI = {"MY": "MYR", "US": "USD"}


def _sahkan_kuantiti(pasaran, kuantiti):
    """Bursa Malaysia (MY) berdagang dalam unit bulat sahaja; pasaran lain (cth US)
    boleh berdagang pecahan (saham serpihan) - bundarkan hanya untuk pasaran MY,
    walaupun borang/pratonton di hujung pelanggan sudah menyekat ini."""
    kuantiti = float(kuantiti)
    if pasaran == "MY":
        kuantiti = round(kuantiti)
    return kuantiti


@app.route("/transaksi/tambah", methods=["POST"])
def tambah_transaksi():
    db = get_db()
    fee = _borang_fee(request.form)
    pasaran = (request.form.get("pasaran") or "MY").strip().upper()
    mata_wang = PASARAN_MATA_WANG_LALAI.get(pasaran, pasaran)
    db.execute(
        """INSERT INTO transaksi
           (tarikh, masa, pasaran, mata_wang, kaunter, jenis, kuantiti, harga_seunit,
            komisen, yuran_platform, yuran_kliring, duti_setem, sst, caj_lain, nota)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            request.form["tarikh"],
            request.form.get("masa", "").strip(),
            pasaran,
            mata_wang,
            request.form["kaunter"].strip().upper(),
            request.form["jenis"],
            _sahkan_kuantiti(pasaran, request.form["kuantiti"]),
            float(request.form["harga_seunit"]),
            fee["komisen"], fee["yuran_platform"], fee["yuran_kliring"],
            fee["duti_setem"], fee["sst"], fee["caj_lain"],
            request.form.get("nota", "").strip(),
        ),
    )
    db.commit()
    return redirect(url_for("senarai_transaksi"))


@app.route("/transaksi/<int:transaksi_id>/edit", methods=["GET", "POST"])
def edit_transaksi(transaksi_id):
    db = get_db()
    if request.method == "POST":
        fee = _borang_fee(request.form)
        pasaran = (request.form.get("pasaran") or "MY").strip().upper()
        mata_wang = PASARAN_MATA_WANG_LALAI.get(pasaran, pasaran)
        db.execute(
            """UPDATE transaksi
               SET tarikh = ?, masa = ?, pasaran = ?, mata_wang = ?, kaunter = ?, jenis = ?,
                   kuantiti = ?, harga_seunit = ?,
                   komisen = ?, yuran_platform = ?, yuran_kliring = ?, duti_setem = ?, sst = ?, caj_lain = ?,
                   nota = ?
               WHERE id = ?""",
            (
                request.form["tarikh"],
                request.form.get("masa", "").strip(),
                pasaran,
                mata_wang,
                request.form["kaunter"].strip().upper(),
                request.form["jenis"],
                _sahkan_kuantiti(pasaran, request.form["kuantiti"]),
                float(request.form["harga_seunit"]),
                fee["komisen"], fee["yuran_platform"], fee["yuran_kliring"],
                fee["duti_setem"], fee["sst"], fee["caj_lain"],
                request.form.get("nota", "").strip(),
                transaksi_id,
            ),
        )
        db.commit()
        return redirect(url_for("senarai_transaksi"))

    t = db.execute("SELECT * FROM transaksi WHERE id = ?", (transaksi_id,)).fetchone()
    return render_template("edit_transaksi.html", t=t)


@app.route("/transaksi/<int:transaksi_id>/padam", methods=["POST"])
def padam_transaksi(transaksi_id):
    db = get_db()
    db.execute("DELETE FROM transaksi WHERE id = ?", (transaksi_id,))
    db.commit()
    return redirect(url_for("senarai_transaksi"))


@app.route("/modal")
def senarai_modal():
    db = get_db()
    modal = muat_semua_modal(db)
    modal.sort(key=lambda m: (m["tarikh"], m["id"]), reverse=True)

    jumlah_deposit = sum(m["jumlah"] for m in modal if m["jenis"] == "MASUK")
    jumlah_pengeluaran = sum(m["jumlah"] for m in modal if m["jenis"] == "KELUAR")
    jumlah_modal = jumlah_deposit - jumlah_pengeluaran

    # Modal direkod dalam RM, jadi hanya pasaran MY diambil kira di sini.
    transaksi = muat_semua_transaksi(db)
    tx_my = [t for t in transaksi if t["pasaran"] == "MY"]
    _, portfolio = kira_ledger(tx_my)
    nilai_pelaburan = sum(p["nilai_kos"] for p in portfolio.values())
    tunai = kira_tunai(tx_my, modal)

    return render_template(
        "modal.html",
        modal=modal,
        jumlah_deposit=round(jumlah_deposit, 2),
        jumlah_pengeluaran=round(jumlah_pengeluaran, 2),
        jumlah_modal=round(jumlah_modal, 2),
        nilai_pelaburan=round(nilai_pelaburan, 2),
        baki_tunai=tunai["baki_tunai"],
        hari_ini=date.today().isoformat(),
    )


@app.route("/modal/tambah", methods=["POST"])
def tambah_modal():
    db = get_db()
    db.execute(
        """INSERT INTO modal (tarikh, jenis, jumlah, nota) VALUES (?, ?, ?, ?)""",
        (
            request.form["tarikh"],
            request.form["jenis"],
            float(request.form["jumlah"]),
            request.form.get("nota", "").strip(),
        ),
    )
    db.commit()
    return redirect(url_for("senarai_modal"))


@app.route("/modal/<int:modal_id>/edit", methods=["GET", "POST"])
def edit_modal(modal_id):
    db = get_db()
    if request.method == "POST":
        db.execute(
            """UPDATE modal SET tarikh = ?, jenis = ?, jumlah = ?, nota = ? WHERE id = ?""",
            (
                request.form["tarikh"],
                request.form["jenis"],
                float(request.form["jumlah"]),
                request.form.get("nota", "").strip(),
                modal_id,
            ),
        )
        db.commit()
        return redirect(url_for("senarai_modal"))

    m = db.execute("SELECT * FROM modal WHERE id = ?", (modal_id,)).fetchone()
    return render_template("edit_modal.html", m=m)


@app.route("/modal/<int:modal_id>/padam", methods=["POST"])
def padam_modal(modal_id):
    db = get_db()
    db.execute("DELETE FROM modal WHERE id = ?", (modal_id,))
    db.commit()
    return redirect(url_for("senarai_modal"))


@app.route("/transaksi/import", methods=["GET"])
def import_csv_borang():
    return render_template("import_csv.html")


@app.route("/transaksi/import/pratonton", methods=["POST"])
def import_csv_pratonton():
    fail = request.files.get("fail_csv")
    if not fail or fail.filename == "":
        return render_template("import_csv.html", ralat="Sila pilih fail CSV terlebih dahulu.")

    try:
        teks = fail.read().decode("utf-8-sig")
        baris = parse_moomoo_csv(teks)
    except Exception:
        return render_template(
            "import_csv.html",
            ralat="Fail CSV tidak dapat dibaca. Pastikan ia fail eksport History Transactions dari moomoo.",
        )

    if not baris:
        return render_template(
            "import_csv.html", ralat="Tiada transaksi sah dijumpai dalam fail ini."
        )

    db = get_db()
    tandakan_mungkin_pendua(baris, muat_semua_transaksi(db))

    return render_template("import_csv_pratonton.html", baris=baris)


# Toleransi tarikh (hari) bila kesan pendua. Pesanan Stop/Trigger moomoo kadang
# guna "Order Time" (masa pesanan diletak) yang boleh berbeza beberapa hari
# daripada masa sebenar ia dipenuhi - jadi padanan tarikh tepat tak mencukupi.
HARI_TOLERANSI_PENDUA = 7


def tandakan_mungkin_pendua(baris_baharu, transaksi_sedia_ada):
    """Tandakan setiap baris dalam baris_baharu dengan "mungkin_pendua" (bool)
    jika ada transaksi sedia ada dengan kaunter/jenis/kuantiti/harga sama dan
    tarikh dalam lingkungan HARI_TOLERANSI_PENDUA hari.
    """
    sedia_ada_oleh_kunci = {}
    for t in transaksi_sedia_ada:
        kunci = (t["kaunter"], t["jenis"], t["kuantiti"], round(t["harga_seunit"], 4))
        sedia_ada_oleh_kunci.setdefault(kunci, []).append(t["tarikh"])

    for b in baris_baharu:
        kunci = (b["kaunter"], b["jenis"], b["kuantiti"], round(b["harga_seunit"], 4))
        tarikh_sepadan = sedia_ada_oleh_kunci.get(kunci, [])
        tarikh_b = date.fromisoformat(b["tarikh"])
        b["mungkin_pendua"] = any(
            abs((tarikh_b - date.fromisoformat(t_tarikh)).days) <= HARI_TOLERANSI_PENDUA
            for t_tarikh in tarikh_sepadan
        )


@app.route("/transaksi/import/sahkan", methods=["POST"])
def import_csv_sahkan():
    pilih = request.form.getlist("pilih")
    db = get_db()
    jumlah = 0
    for i in pilih:
        tarikh = request.form.get(f"tarikh_{i}")
        kaunter = request.form.get(f"kaunter_{i}")
        jenis = request.form.get(f"jenis_{i}")
        kuantiti = request.form.get(f"kuantiti_{i}")
        harga = request.form.get(f"harga_{i}")
        masa = request.form.get(f"masa_{i}", "")
        pasaran = (request.form.get(f"pasaran_{i}") or "MY").strip().upper()
        mata_wang = (request.form.get(f"mata_wang_{i}") or PASARAN_MATA_WANG_LALAI.get(pasaran, pasaran)).strip().upper()
        nota = request.form.get(f"nota_{i}", "")
        if not (tarikh and kaunter and jenis and kuantiti and harga):
            continue
        fee = _borang_fee(request.form, indeks=i)
        db.execute(
            """INSERT INTO transaksi
               (tarikh, masa, pasaran, mata_wang, kaunter, jenis, kuantiti, harga_seunit,
                komisen, yuran_platform, yuran_kliring, duti_setem, sst, caj_lain, nota)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                tarikh, masa, pasaran, mata_wang, kaunter.strip().upper(), jenis,
                _sahkan_kuantiti(pasaran, kuantiti), float(harga),
                fee["komisen"], fee["yuran_platform"], fee["yuran_kliring"],
                fee["duti_setem"], fee["sst"], fee["caj_lain"], nota,
            ),
        )
        jumlah += 1
    db.commit()
    return redirect(url_for("senarai_transaksi", diimport=jumlah))


@app.route("/laporan")
def laporan_untung_rugi():
    db = get_db()
    transaksi = muat_semua_transaksi(db)
    ledger, _ = kira_ledger_ikut_pasaran(transaksi)
    jualan = [b for b in ledger if b["jenis"] == "JUAL"]
    jualan.sort(key=lambda t: (t["tarikh"], t["masa"], t["id"]), reverse=True)

    for b in jualan:
        kos_asas = b["kos_purata_sebelum"] * b["kuantiti"]
        b["peratus_untung_rugi"] = (
            round((b["untung_rugi"] / kos_asas) * 100, 2) if kos_asas > 0 else None
        )
        b["simbol"] = simbol_mata_wang(b["mata_wang"])

    # Ringkasan dikira BERASINGAN ikut pasaran - RM dan USD tak boleh dijumlahkan terus.
    ringkasan_pasaran = []
    for p in sorted({t["pasaran"] for t in transaksi}):
        jualan_p = [b for b in jualan if b["pasaran"] == p]
        if not jualan_p:
            continue
        jumlah_untung_p = sum(b["untung_rugi"] for b in jualan_p if b["untung_rugi"] > 0)
        jumlah_rugi_p = sum(b["untung_rugi"] for b in jualan_p if b["untung_rugi"] < 0)
        ringkasan_pasaran.append({
            "pasaran": p,
            "simbol": jualan_p[0]["simbol"],
            "jumlah_untung": round(jumlah_untung_p, 2),
            "jumlah_rugi": round(jumlah_rugi_p, 2),
            "jumlah_untung_rugi": round(jumlah_untung_p + jumlah_rugi_p, 2),
            "bilangan_untung": sum(1 for b in jualan_p if b["untung_rugi"] > 0),
            "bilangan_rugi": sum(1 for b in jualan_p if b["untung_rugi"] < 0),
            "bilangan_jualan": len(jualan_p),
        })

    return render_template(
        "laporan.html",
        jualan=jualan,
        ringkasan_pasaran=ringkasan_pasaran,
        bilangan_jualan=len(jualan),
    )


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(debug=True)
