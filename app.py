import os
import sqlite3
from datetime import date

from flask import Flask, g, redirect, render_template, request, url_for

from portfolio import kira_ledger

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


@app.route("/")
def dashboard():
    db = get_db()
    transaksi = muat_semua_transaksi(db)
    ledger, portfolio = kira_ledger(transaksi)

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
    )


@app.route("/transaksi")
def senarai_transaksi():
    db = get_db()
    transaksi = muat_semua_transaksi(db)
    ledger, _ = kira_ledger(transaksi)
    ledger.sort(key=lambda t: (t["tarikh"], t["id"]), reverse=True)
    return render_template(
        "transaksi.html", ledger=ledger, hari_ini=date.today().isoformat()
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


@app.route("/laporan")
def laporan_untung_rugi():
    db = get_db()
    transaksi = muat_semua_transaksi(db)
    ledger, _ = kira_ledger(transaksi)
    jualan = [b for b in ledger if b["jenis"] == "JUAL"]
    jualan.sort(key=lambda t: (t["tarikh"], t["id"]), reverse=True)

    jumlah_untung_rugi = sum(b["untung_rugi"] for b in jualan)
    jumlah_untung = sum(b["untung_rugi"] for b in jualan if b["untung_rugi"] > 0)
    jumlah_rugi = sum(b["untung_rugi"] for b in jualan if b["untung_rugi"] < 0)

    return render_template(
        "laporan.html",
        jualan=jualan,
        jumlah_untung_rugi=round(jumlah_untung_rugi, 2),
        jumlah_untung=round(jumlah_untung, 2),
        jumlah_rugi=round(jumlah_rugi, 2),
    )


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(debug=True)
