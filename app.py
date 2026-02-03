from flask import Flask, render_template, request, redirect, send_file
import mysql.connector
from fpdf import FPDF
from datetime import datetime
import os

app = Flask(__name__)

# Koneksi Database
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="db_rawat_inap_rino"
)
cursor = db.cursor(dictionary=True)

# INDEX
@app.route("/")
def index():
    cursor.execute("""
        SELECT 
            t.id_transaksi_rino,
            p.nama_rino,
            k.kelas_rino AS status_kamar,
            r.tgl_masuk_rino,
            r.tgl_keluar_rino,
            t.total_biaya_rino,
            t.status_pembayaran_rino
        FROM transaksi_rino t
        JOIN pasien_rino p ON t.id_pasien_rino = p.id_pasien_rino
        LEFT JOIN rawat_inap_rino r ON t.id_rawat_rino = r.id_rawat_rino
        LEFT JOIN kamar_rino k ON r.id_kamar_rino = k.id_kamar_rino
    """)
    data = cursor.fetchall()
    return render_template("index_rino.html", data=data)

# TAMBAH TRANSAKSI
@app.route("/tambah", methods=["GET", "POST"])
def tambah():
    cursor.execute("SELECT id_pasien_rino, nama_rino FROM pasien_rino")
    pasien = cursor.fetchall()
    cursor.execute("""
        SELECT r.id_rawat_rino, r.id_pasien_rino, r.id_kamar_rino, 
               r.tgl_masuk_rino, r.tgl_keluar_rino, k.kelas_rino, k.status_kamar_rino
        FROM rawat_inap_rino r 
        JOIN kamar_rino k ON r.id_kamar_rino = k.id_kamar_rino
    """)
    rawat_inap = cursor.fetchall()

    if request.method == "POST":
        id_pasien = request.form["pasien"]

        # Jika tambah pasien baru
        if id_pasien == "tambah":
            nama_baru = request.form["nama_baru"]
            alamat_baru = request.form["alamat_baru"]
            kontak_baru = request.form["kontak_baru"]

            cursor.execute("""
                INSERT INTO pasien_rino (nama_rino, alamat_rino, kontak_rino)
                VALUES (%s, %s, %s)
            """, (nama_baru, alamat_baru, kontak_baru))
            db.commit()
            id_pasien = cursor.lastrowid

            # otomatis buat rawat inap baru untuk pasien ini
            cursor.execute("""
                INSERT INTO rawat_inap_rino (id_pasien_rino, id_kamar_rino, tgl_masuk_rino)
                VALUES (%s, NULL, %s)
            """, (id_pasien, datetime.now().date()))
            db.commit()

        id_rawat = request.form.get("rawat_inap")  # bisa kosong
        status = request.form["status"]
        tgl_masuk = request.form.get("tgl_masuk")
        tgl_keluar = request.form.get("tgl_keluar")

        total = 0

        if id_rawat:  # kalau pilih rawat inap
            cursor.execute("""
                UPDATE rawat_inap_rino SET
                    tgl_masuk_rino=%s,
                    tgl_keluar_rino=%s
                WHERE id_rawat_rino=%s
            """, (tgl_masuk, tgl_keluar if tgl_keluar else None, id_rawat))
            db.commit()

            cursor.execute("""
                SELECT tgl_masuk_rino, tgl_keluar_rino, id_kamar_rino 
                FROM rawat_inap_rino WHERE id_rawat_rino=%s
            """, (id_rawat,))
            rawat = cursor.fetchone()

            if rawat:
                masuk = datetime.strptime(str(rawat["tgl_masuk_rino"]), "%Y-%m-%d")
                keluar = datetime.strptime(str(rawat["tgl_keluar_rino"]), "%Y-%m-%d") if rawat["tgl_keluar_rino"] else masuk
                lama = max((keluar - masuk).days, 1)

                cursor.execute("SELECT harga_rino, status_kamar_rino FROM kamar_rino WHERE id_kamar_rino=%s", (rawat["id_kamar_rino"],))
                kamar = cursor.fetchone()

                if kamar and kamar["status_kamar_rino"] != "Terisi":
                    total = int(kamar["harga_rino"]) * lama
                else:
                    return "❌ Kamar sudah terisi!"

        # Insert transaksi (tanpa kolom tgl_rino, gunakan created_at otomatis)
        cursor.execute("""
            INSERT INTO transaksi_rino 
            (id_pasien_rino, id_rawat_rino, total_biaya_rino, status_pembayaran_rino)
            VALUES (%s, %s, %s, %s)
        """, (id_pasien, id_rawat if id_rawat else None, total, status))
        db.commit()
        return redirect("/")

    return render_template("form_rino.html", pasien=pasien, rawat_inap=rawat_inap)    

# EDIT TRANSAKSI
@app.route("/edit/<id>", methods=["GET", "POST"])
def edit(id):
    # Ambil data pasien
    cursor.execute("SELECT id_pasien_rino, nama_rino FROM pasien_rino")
    pasien = cursor.fetchall()

    # Ambil data rawat inap + kamar
    cursor.execute("""
        SELECT r.id_rawat_rino, r.id_pasien_rino, r.id_kamar_rino, 
               r.tgl_masuk_rino, r.tgl_keluar_rino, k.kelas_rino, k.status_kamar_rino
        FROM rawat_inap_rino r 
        JOIN kamar_rino k ON r.id_kamar_rino = k.id_kamar_rino
    """)
    rawat_inap = cursor.fetchall()

    if request.method == "POST":
        id_pasien = request.form["pasien"]
        id_rawat = request.form["rawat_inap"]
        tgl_masuk = request.form["tgl_masuk"]
        tgl_keluar = request.form["tgl_keluar"]
        status = request.form["status"]

        # Hitung lama rawat inap
        masuk = datetime.strptime(tgl_masuk, "%Y-%m-%d")
        keluar = datetime.strptime(tgl_keluar, "%Y-%m-%d")
        lama = (keluar - masuk).days

        # Ambil harga kamar
        cursor.execute("SELECT harga_rino, status_kamar_rino FROM kamar_rino WHERE id_kamar_rino=%s", (id_rawat,))
        kamar = cursor.fetchone()
        if kamar["status_kamar_rino"] == "Terisi":
            return "❌ Kamar sudah terisi!"

        total = int(kamar["harga_rino"]) * lama

        # Update transaksi (tanpa tgl_masuk/keluar)
        cursor.execute("""
            UPDATE transaksi_rino SET
                id_pasien_rino=%s,
                id_rawat_rino=%s,
                total_biaya_rino=%s,
                status_pembayaran_rino=%s
            WHERE id_transaksi_rino=%s
        """, (id_pasien, id_rawat, total, status, id))

        # Update tanggal masuk/keluar di tabel rawat inap
        cursor.execute("""
            UPDATE rawat_inap_rino SET
                tgl_masuk_rino=%s,
                tgl_keluar_rino=%s
            WHERE id_rawat_rino=%s
        """, (tgl_masuk, tgl_keluar, id_rawat))

        db.commit()
        return redirect("/")

    cursor.execute("SELECT * FROM transaksi_rino WHERE id_transaksi_rino=%s", (id,))
    data = cursor.fetchone()
    return render_template("update_rino.html", data=data, pasien=pasien, rawat_inap=rawat_inap)


# DELETE
@app.route("/hapus/<id>")
def hapus(id):
    cursor.execute("DELETE FROM transaksi_rino WHERE id_transaksi_rino=%s", (id,))
    db.commit()
    return redirect("/")

# DATA PASIEN
@app.route("/pasien")
def pasien():
    cursor.execute("SELECT * FROM pasien_rino")
    data = cursor.fetchall()
    return render_template("pasien_rino.html", pasien=data)

# CETAK PDF PASIEN
@app.route("/cetak_pasien")
def cetak_pasien():
    cursor.execute("SELECT id_pasien_rino, nama_rino FROM pasien_rino")
    data = cursor.fetchall()

    class PDF(FPDF):
        def header(self):
            self.set_font('DejaVu', '', 16)
            self.set_text_color(30, 64, 175)
            self.cell(0, 10, "Laporan Data Pasien", ln=True, align='C')
            self.ln(2)
            self.set_draw_color(30, 64, 175)
            self.set_line_width(1)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(4)

        def footer(self):
            self.set_y(-15)
            self.set_font('DejaVu', '', 10)
            self.set_text_color(100, 100, 100)
            self.cell(0, 10, f'Halaman {self.page_no()}', align='C')

    pdf = PDF()
    # Tambahkan font SEBELUM add_page()
    pdf.add_font('DejaVu', '', os.path.join('fonts', 'DejaVuSans.ttf'), uni=True)
    pdf.set_font('DejaVu', '', 12)
    pdf.add_page()
    # Table header
    pdf.set_fill_color(30, 64, 175)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(40, 10, "ID Pasien", border=1, align='C', fill=True)
    pdf.cell(120, 10, "Nama Pasien", border=1, align='C', fill=True)
    pdf.ln()
    # Table body
    pdf.set_text_color(0, 0, 0)
    for row in data:
        pdf.cell(40, 10, str(row['id_pasien_rino']), border=1, align='C')
        pdf.cell(120, 10, row['nama_rino'], border=1)
        pdf.ln()
    pdf_path = "laporan_pasien.pdf"
    pdf.output(pdf_path)
    return send_file(pdf_path, as_attachment=True)

# CETAK LAPORAN SEMUA TRANSAKSI
@app.route("/cetak_transaksi")
def cetak_transaksi():
    cursor.execute("""
        SELECT 
            t.id_transaksi_rino,
            p.nama_rino,
            k.kelas_rino,
            r.tgl_masuk_rino,
            r.tgl_keluar_rino,
            t.total_biaya_rino,
            t.status_pembayaran_rino
        FROM transaksi_rino t
        JOIN pasien_rino p ON t.id_pasien_rino = p.id_pasien_rino
        JOIN rawat_inap_rino r ON t.id_rawat_rino = r.id_rawat_rino
        JOIN kamar_rino k ON r.id_kamar_rino = k.id_kamar_rino
    """)
    data = cursor.fetchall()

    class PDF(FPDF):
        def header(self):
            self.set_font('Arial', 'B', 14)
            self.cell(0, 10, "Laporan Transaksi Rawat Inap", ln=True, align='C')
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Halaman {self.page_no()}', align='C')

    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=10)

    # Header tabel
    pdf.set_fill_color(30, 64, 175)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(15, 8, "ID", border=1, align='C', fill=True)
    pdf.cell(35, 8, "Pasien", border=1, align='C', fill=True)
    pdf.cell(25, 8, "Kelas", border=1, align='C', fill=True)
    pdf.cell(25, 8, "Masuk", border=1, align='C', fill=True)
    pdf.cell(25, 8, "Keluar", border=1, align='C', fill=True)
    pdf.cell(30, 8, "Biaya", border=1, align='C', fill=True)
    pdf.cell(30, 8, "Status", border=1, align='C', fill=True)
    pdf.ln()

    # Isi tabel
    pdf.set_text_color(0, 0, 0)
    for row in data:
        pdf.cell(15, 8, str(row['id_transaksi_rino']), border=1, align='C')
        pdf.cell(35, 8, row['nama_rino'], border=1)
        pdf.cell(25, 8, row['kelas_rino'], border=1)
        pdf.cell(25, 8, str(row['tgl_masuk_rino']), border=1)
        pdf.cell(25, 8, str(row['tgl_keluar_rino']), border=1)
        pdf.cell(30, 8, f"Rp {int(row['total_biaya_rino']):,}", border=1)
        pdf.cell(30, 8, row['status_pembayaran_rino'], border=1)
        pdf.ln()

    pdf_path = "laporan_transaksi.pdf"
    pdf.output(pdf_path)
    return send_file(pdf_path, as_attachment=True)

# CETAK STRUK PER TRANSAKSI
@app.route("/cetak_struk/<id>")
def cetak_struk(id):
    cursor.execute("""
        SELECT 
            t.id_transaksi_rino,
            p.nama_rino,
            k.kelas_rino,
            r.tgl_masuk_rino,
            r.tgl_keluar_rino,
            t.total_biaya_rino,
            t.status_pembayaran_rino
        FROM transaksi_rino t
        JOIN pasien_rino p ON t.id_pasien_rino = p.id_pasien_rino
        JOIN rawat_inap_rino r ON t.id_rawat_rino = r.id_rawat_rino
        JOIN kamar_rino k ON r.id_kamar_rino = k.id_kamar_rino
        WHERE t.id_transaksi_rino=%s
    """, (id,))
    transaksi = cursor.fetchone()

    if not transaksi:
        return "❌ Transaksi tidak ditemukan!"

    pdf = FPDF('P', 'mm', (80, 150))  # ukuran kecil ala struk
    pdf.add_page()

    # Header
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 8, "Rumah Sakit rino", ln=True, align='C')
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 5, "Jl. Contoh No.123, Bandung", ln=True, align='C')
    pdf.cell(0, 5, "Telp: (021) 1234567", ln=True, align='C')
    pdf.ln(5)
    pdf.cell(0, 5, "=== STRUK PEMBAYARAN RAWAT INAP ===", ln=True, align='C')
    pdf.ln(5)

    # Isi
    pdf.set_font("Arial", '', 10)
    pdf.cell(35, 6, "ID Transaksi", 0, 0)
    pdf.cell(40, 6, f": {transaksi['id_transaksi_rino']}", 0, 1)
    pdf.cell(35, 6, "Nama Pasien", 0, 0)
    pdf.cell(40, 6, f": {transaksi['nama_rino']}", 0, 1)
    pdf.cell(35, 6, "Kelas Kamar", 0, 0)
    pdf.cell(40, 6, f": {transaksi['kelas_rino']}", 0, 1)
    pdf.cell(35, 6, "Tanggal Masuk", 0, 0)
    pdf.cell(40, 6, f": {transaksi['tgl_masuk_rino']}", 0, 1)
    pdf.cell(35, 6, "Tanggal Keluar", 0, 0)
    pdf.cell(40, 6, f": {transaksi['tgl_keluar_rino']}", 0, 1)
    pdf.cell(35, 6, "Total Biaya", 0, 0)
    pdf.cell(40, 6, f": Rp {int(transaksi['total_biaya_rino']):,}", 0, 1)
    pdf.cell(35, 6, "Status Bayar", 0, 0)
    pdf.cell(40, 6, f": {transaksi['status_pembayaran_rino']}", 0, 1)

    # Footer
    pdf.ln(10)
    pdf.cell(0, 5, "--------------------------------", ln=True, align='C')
    pdf.cell(0, 5, "Terima kasih atas kunjungan Anda", ln=True, align='C')
    pdf.cell(0, 5, "Semoga lekas sembuh 🙏", ln=True, align='C')

    pdf_path = f"struk_{id}.pdf"
    pdf.output(pdf_path)
    return send_file(pdf_path, as_attachment=True)

if __name__ == "__main__":
    app.run(debug=True)
