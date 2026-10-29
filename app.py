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


def muat_semua_transaksi(db):
    rows = db.execute(
        "SELECT * FROM transaksi ORDER BY tarikh ASC, id ASC"
    ).fetchall()
    return [dict(r) for r in rows]


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


@app.route("/")
def dashboard():
    db = get_db()
    transaksi = muat_semua_transaksi(db)
    modal = muat_semua_modal(db)
    ledger, portfolio = kira_ledger(transaksi)
    tunai = kira_tunai(transaksi, modal)

    jumlah_untung_rugi = sum(
        b["untung_rugi"] for b in ledger if b["untung_rugi"] is not None
    )
    jumlah_nilai_kos = sum(p["nilai_kos"] for p in portfolio.values())

    portfolio_senarai = sorted(
        ({"kaunter": k, **v} for k, v in portfolio.items()),
        key=lambda x: x["kaunter"],
    )

    return render_template(
        "dashboard.html",
        portfolio=portfolio_senarai,
        jumlah_untung_rugi=round(jumlah_untung_rugi, 2),
        jumlah_nilai_kos=round(jumlah_nilai_kos, 2),
        bilangan_kaunter=len(portfolio),
        jumlah_modal=tunai["jumlah_modal"],
        baki_tunai=tunai["baki_tunai"],
    )


@app.route("/transaksi")
def senarai_transaksi():
    db = get_db()
    transaksi = muat_semua_transaksi(db)
    ledger, _ = kira_ledger(transaksi)

    senarai_kaunter = sorted({t["kaunter"] for t in transaksi})

    if "dari" in request.args:
        # Borang tapisan dihantar (termasuk "Kosongkan Tapisan") - guna terus apa yang dihantar.
        f_dari = request.args.get("dari", "").strip()
        f_hingga = request.args.get("hingga", "").strip()
    else:
        # Lawatan pertama / klik nav - lalai tapis kepada bulan semasa.
        f_dari, f_hingga = julat_bulan_semasa()
    f_kaunter = request.args.get("kaunter", "").strip().upper()

    ledger_tapis = ledger
    if f_dari:
        ledger_tapis = [t for t in ledger_tapis if t["tarikh"] >= f_dari]
    if f_hingga:
        ledger_tapis = [t for t in ledger_tapis if t["tarikh"] <= f_hingga]
    if f_kaunter:
        ledger_tapis = [t for t in ledger_tapis if t["kaunter"] == f_kaunter]

    ledger_tapis.sort(key=lambda t: (t["tarikh"], t["id"]), reverse=True)
    diimport = request.args.get("diimport", type=int)
    return render_template(
        "transaksi.html",
        ledger=ledger_tapis,
        hari_ini=date.today().isoformat(),
        diimport=diimport,
        senarai_kaunter=senarai_kaunter,
        f_dari=f_dari,
        f_hingga=f_hingga,
        f_kaunter=f_kaunter,
        ada_tapisan=bool(f_dari or f_hingga or f_kaunter),
    )


@app.route("/transaksi/tambah", methods=["POST"])
def tambah_transaksi():
    db = get_db()
    db.execute(
        """INSERT INTO transaksi (tarikh, kaunter, jenis, kuantiti, harga_seunit, caj, nota)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            request.form["tarikh"],
            request.form["kaunter"].strip().upper(),
            request.form["jenis"],
            int(request.form["kuantiti"]),
            float(request.form["harga_seunit"]),
            float(request.form.get("caj") or 0),
            request.form.get("nota", "").strip(),
        ),
    )
    db.commit()
    return redirect(url_for("senarai_transaksi"))


@app.route("/transaksi/<int:transaksi_id>/edit", methods=["GET", "POST"])
def edit_transaksi(transaksi_id):
    db = get_db()
    if request.method == "POST":
        db.execute(
            """UPDATE transaksi
               SET tarikh = ?, kaunter = ?, jenis = ?, kuantiti = ?, harga_seunit = ?, caj = ?, nota = ?
               WHERE id = ?""",
            (
                request.form["tarikh"],
                request.form["kaunter"].strip().upper(),
                request.form["jenis"],
                int(request.form["kuantiti"]),
                float(request.form["harga_seunit"]),
                float(request.form.get("caj") or 0),
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

    transaksi = muat_semua_transaksi(db)
    _, portfolio = kira_ledger(transaksi)
    nilai_pelaburan = sum(p["nilai_kos"] for p in portfolio.values())

    return render_template(
        "modal.html",
        modal=modal,
        jumlah_deposit=round(jumlah_deposit, 2),
        jumlah_pengeluaran=round(jumlah_pengeluaran, 2),
        jumlah_modal=round(jumlah_modal, 2),
        nilai_pelaburan=round(nilai_pelaburan, 2),
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
    sedia_ada = {
        (t["tarikh"], t["kaunter"], t["jenis"], t["kuantiti"], round(t["harga_seunit"], 4))
        for t in muat_semua_transaksi(db)
    }
    for b in baris:
        kunci = (b["tarikh"], b["kaunter"], b["jenis"], b["kuantiti"], round(b["harga_seunit"], 4))
        b["mungkin_pendua"] = kunci in sedia_ada

    return render_template("import_csv_pratonton.html", baris=baris)


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
        caj = request.form.get(f"caj_{i}", "0")
        nota = request.form.get(f"nota_{i}", "")
        if not (tarikh and kaunter and jenis and kuantiti and harga):
            continue
        db.execute(
            """INSERT INTO transaksi (tarikh, kaunter, jenis, kuantiti, harga_seunit, caj, nota)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (tarikh, kaunter.strip().upper(), jenis, int(kuantiti), float(harga), float(caj or 0), nota),
        )
        jumlah += 1
    db.commit()
    return redirect(url_for("senarai_transaksi", diimport=jumlah))


@app.route("/laporan")
def laporan_untung_rugi():
    db = get_db()
    transaksi = muat_semua_transaksi(db)
    ledger, _ = kira_ledger(transaksi)
    jualan = [b for b in ledger if b["jenis"] == "JUAL"]
    jualan.sort(key=lambda t: (t["tarikh"], t["id"]), reverse=True)

    for b in jualan:
        kos_asas = b["kos_purata_sebelum"] * b["kuantiti"]
        b["peratus_untung_rugi"] = (
            round((b["untung_rugi"] / kos_asas) * 100, 2) if kos_asas > 0 else None
        )

    jumlah_untung_rugi = sum(b["untung_rugi"] for b in jualan)
    jumlah_untung = sum(b["untung_rugi"] for b in jualan if b["untung_rugi"] > 0)
    jumlah_rugi = sum(b["untung_rugi"] for b in jualan if b["untung_rugi"] < 0)
    bilangan_untung = sum(1 for b in jualan if b["untung_rugi"] > 0)
    bilangan_rugi = sum(1 for b in jualan if b["untung_rugi"] < 0)

    return render_template(
        "laporan.html",
        jualan=jualan,
        jumlah_untung_rugi=round(jumlah_untung_rugi, 2),
        jumlah_untung=round(jumlah_untung, 2),
        jumlah_rugi=round(jumlah_rugi, 2),
        bilangan_untung=bilangan_untung,
        bilangan_rugi=bilangan_rugi,
        bilangan_jualan=len(jualan),
    )


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(debug=True)
