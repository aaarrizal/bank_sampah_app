import streamlit as st
import pandas as pd
import sqlite3
import random
import string
from datetime import datetime

# ==========================================
# 1. PENGATURAN HALAMAN & CUSTOM CSS
# ==========================================
st.set_page_config(page_title="Sistem Bank Sampah", page_icon="♻️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    div[data-testid="metric-container"] {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        padding: 15px 20px;
        border-radius: 12px;
        box-shadow: 2px 4px 10px rgba(0,0,0,0.05);
    }
    </style>
""", unsafe_allow_html=True)

# KONFIGURASI HARGA SAMPAH (DIKUNCI OLEH SISTEM)
HARGA_SAMPAH = {
    "Plastik Botol / Gelas": 3000,
    "Kertas / Kardus Bekas": 2000,
    "Besi / Logam / Kuningan": 6000,
    "Minyak Jelantah (per Liter)": 5000,
    "Sampah Organik (Kompos)": 1000
}

# ==========================================
# 2. INISIALISASI DATABASE SQLITE
# ==========================================
def get_db_connection():
    return sqlite3.connect('banksampah.db', check_same_thread=False)

def init_db():
    conn = get_db_connection()
    c = conn.cursor()
    # Tabel Nasabah
    c.execute('''
        CREATE TABLE IF NOT EXISTS nasabah (
            username TEXT PRIMARY KEY,
            nama TEXT,
            alamat TEXT,
            no_hp TEXT,
            saldo INTEGER,
            password TEXT
        )
    ''')
    # Tabel Admin
    c.execute('''
        CREATE TABLE IF NOT EXISTS admin (
            id INTEGER PRIMARY KEY,
            username TEXT,
            password TEXT
        )
    ''')
    # Tabel Transaksi (Diperluas dengan kolom Keterangan Log Audit)
    c.execute('''
        CREATE TABLE IF NOT EXISTS transaksi (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            jenis TEXT,
            nominal INTEGER,
            waktu TEXT,
            keterangan TEXT
        )
    ''')
    # Tabel Pengajuan Tarik Tunai (QR / VA)
    c.execute('''
        CREATE TABLE IF NOT EXISTS pengajuan_tarik (
            token_va TEXT PRIMARY KEY,
            username TEXT,
            nominal INTEGER,
            waktu TEXT,
            status TEXT
        )
    ''')
    
    # Akun Admin Default
    c.execute("SELECT * FROM admin WHERE id=1")
    if c.fetchone() is None:
        c.execute("INSERT INTO admin (id, username, password) VALUES (1, 'admin', 'sampahjadiemas')")
        
    conn.commit()
    conn.close()

init_db()

# --- Fungsi Bantuan Database ---
def get_data_nasabah():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT username, nama, alamat, no_hp, saldo FROM nasabah", conn)
    conn.close()
    df.columns = ["Username", "Nama", "Alamat", "No HP", "Saldo (Rp)"]
    return df

def get_nasabah_detail(username):
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT nama, alamat, no_hp, saldo, password FROM nasabah WHERE username=?", (username,))
    row = c.fetchone()
    conn.close()
    return row

def get_admin_credentials():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("SELECT username, password FROM admin WHERE id=1")
    row = c.fetchone()
    conn.close()
    return row[0], row[1]

def catat_transaksi(username, jenis, nominal, keterangan=""):
    conn = get_db_connection()
    c = conn.cursor()
    waktu_sekarang = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO transaksi (username, jenis, nominal, waktu, keterangan) VALUES (?, ?, ?, ?, ?)", 
              (username, jenis, nominal, waktu_sekarang, keterangan))
    conn.commit()
    conn.close()

def get_history(username=None):
    conn = get_db_connection()
    if username:
        df = pd.read_sql_query("SELECT waktu, jenis, nominal, keterangan FROM transaksi WHERE username=? ORDER BY waktu DESC", conn, params=(username,))
        df.columns = ["Waktu Transaksi", "Jenis", "Nominal (Rp)", "Detail Log"]
    else:
        df = pd.read_sql_query("SELECT waktu, username, jenis, nominal, keterangan FROM transaksi ORDER BY waktu DESC", conn)
        df.columns = ["Waktu Transaksi", "Username", "Jenis", "Nominal (Rp)", "Detail Log"]
    conn.close()
    return df

# --- Fungsi Fitur Tarik QR/VA ---
def buat_token_va():
    acak = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"VA-{acak}"

def simpan_pengajuan_tarik(username, nominal):
    token = buat_token_va()
    conn = get_db_connection()
    c = conn.cursor()
    waktu = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO pengajuan_tarik (token_va, username, nominal, waktu, status) VALUES (?, ?, ?, ?, 'PENDING')",
              (token, username, nominal, waktu))
    conn.commit()
    conn.close()
    return token

def get_pengajuan_aktif_nasabah(username):
    conn = get_db_connection()
    df = pd.read_sql_query(
        "SELECT token_va, nominal, waktu, status FROM pengajuan_tarik WHERE username=? AND status='PENDING' ORDER BY waktu DESC", 
        conn, 
        params=(username,)
    )
    conn.close()
    
    aktif_rows = []
    for idx, row in df.iterrows():
        waktu_buat = datetime.strptime(row['waktu'], "%Y-%m-%d %H:%M:%S")
        selisih_jam = (datetime.now() - waktu_buat).total_seconds() / 3600
        
        if selisih_jam <= 24:
            aktif_rows.append(row)
        else:
            conn_update = get_db_connection()
            c_update = conn_update.cursor()
            c_update.execute("UPDATE pengajuan_tarik SET status='EXPIRED' WHERE token_va=?", (row['token_va'],))
            conn_update.commit()
            conn_update.close()
            
    if len(aktif_rows) > 0:
        return pd.DataFrame(aktif_rows)
    else:
        return pd.DataFrame(columns=["token_va", "nominal", "waktu", "status"])


# ==========================================
# 3. KONFIGURASI SYSTEM SESSION
# ==========================================
if 'user_role' not in st.session_state:
    st.session_state.user_role = None 
if 'current_user_id' not in st.session_state:
    st.session_state.current_user_id = None
if 'current_user_name' not in st.session_state:
    st.session_state.current_user_name = None
if 'menu_aktif' not in st.session_state:
    st.session_state.menu_aktif = ""


# ==========================================
# 4. FITUR POP-UP ADMIN (DIALOGS)
# ==========================================
@st.dialog("✏️ Kelola Akun & Password Nasabah")
def pop_up_edit_admin(username):
    data = get_nasabah_detail(username)
    nama_baru = st.text_input("Nama Lengkap Nasabah", value=data[0])
    alamat_baru = st.text_area("Alamat", value=data[1])
    no_hp_baru = st.text_input("Nomor HP / WhatsApp", value=data[2])
    password_baru = st.text_input("Ubah Password Nasabah", value=data[4], type="password")
    
    st.write("")
    col1, col2 = st.columns(2)
    if col1.button("Simpan Perubahan", use_container_width=True, type="primary"):
        if len(password_baru) < 6:
            st.error("❌ Gagal! Password minimal 6 karakter.")
        elif not nama_baru or not no_hp_baru or not alamat_baru:
            st.error("❌ Semua data wajib diisi!")
        else:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("UPDATE nasabah SET nama=?, alamat=?, no_hp=?, password=? WHERE username=?", 
                      (nama_baru, alamat_baru, no_hp_baru, password_baru, username))
            conn.commit()
            conn.close()
            st.success("Akun nasabah berhasil diperbarui!")
            st.rerun()
    if col2.button("Batal", use_container_width=True):
        st.rerun()

@st.dialog("⚠️ Hapus Nasabah")
def pop_up_hapus(username, nama, saldo):
    st.warning(f"Menghapus nasabah **{nama}** ({username}).")
    st.error(f"Sisa saldo: **Rp {saldo:,.0f}** akan ikut terhapus.")
    
    st.write("")
    col1, col2 = st.columns(2)
    if col1.button("Hapus Permanen", use_container_width=True, type="primary"):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM nasabah WHERE username=?", (username,))
        c.execute("DELETE FROM transaksi WHERE username=?", (username,))
        c.execute("DELETE FROM pengajuan_tarik WHERE username=?", (username,))
        conn.commit()
        conn.close()
        st.success("Nasabah dihapus!")
        st.rerun()
    if col2.button("Batal", use_container_width=True):
        st.rerun()


# ==========================================
# 5. HALAMAN AUTENTIKASI (LOGIN & DAFTAR)
# ==========================================
def halaman_auth():
    st.write("<br><br>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col2:
        st.markdown("<h1 style='text-align: center; color: #2E7D32;'>♻️ EcoBank</h1>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; margin-bottom: 30px;'>Portal Tabungan Bank Sampah Digital</p>", unsafe_allow_html=True)
        
        tab_nasabah, tab_daftar, tab_admin = st.tabs(["👤 Masuk Nasabah", "📝 Daftar Nasabah", "🛠️ Masuk Admin"])
        
        with tab_nasabah:
            with st.form("form_login_nasabah"):
                id_login = st.text_input("Username Nasabah")
                pass_login = st.text_input("Password", type="password")
                btn_login_nasabah = st.form_submit_button("Masuk ke Dasbor Saya", use_container_width=True, type="primary")
                
                if btn_login_nasabah:
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("SELECT nama FROM nasabah WHERE username=? AND password=?", (id_login.strip(), pass_login))
                    result = c.fetchone()
                    conn.close()
                    if result:
                        st.session_state.user_role = "nasabah"
                        st.session_state.current_user_id = id_login.strip()
                        st.session_state.current_user_name = result[0]
                        st.session_state.menu_aktif = "cek_saldo"
                        st.rerun()
                    else:
                        st.error("Username atau Password salah!")

        with tab_daftar:
            with st.form("form_daftar_mandiri"):
                st.info("Buat akun untuk memantau saldo tabungan sampah Anda.")
                reg_user = st.text_input("Buat Username (Harus Unik, Tanpa Spasi)")
                reg_nama = st.text_input("Nama Lengkap")
                reg_hp = st.text_input("Nomor HP / WA")
                reg_alamat = st.text_area("Alamat")
                reg_pass = st.text_input("Buat Password", type="password")
                btn_daftar = st.form_submit_button("Daftar Sekarang", use_container_width=True)
                
                if btn_daftar:
                    if reg_user and reg_nama and reg_hp and reg_alamat and reg_pass:
                        reg_user_clean = reg_user.strip().replace(" ", "")
                        if len(reg_pass) < 6:
                            st.error("❌ Pendaftaran Gagal! Password harus minimal 6 karakter.")
                        else:
                            conn = get_db_connection()
                            c = conn.cursor()
                            c.execute("SELECT username FROM nasabah WHERE username=?", (reg_user_clean,))
                            if c.fetchone():
                                st.error("❌ Username sudah dipakai! Silakan cari nama lain.")
                            else:
                                c.execute("INSERT INTO nasabah (username, nama, alamat, no_hp, saldo, password) VALUES (?, ?, ?, ?, ?, ?)", 
                                          (reg_user_clean, reg_nama, reg_alamat, reg_hp, 0, reg_pass))
                                conn.commit()
                                st.success(f"Pendaftaran Berhasil! Username Anda: **{reg_user_clean}**")
                            conn.close()
                    else:
                        st.error("Mohon lengkapi semua data pendaftaran.")

        with tab_admin:
            with st.form("form_login_admin"):
                admin_user = st.text_input("Username Admin")
                admin_pass = st.text_input("Password Admin", type="password")
                btn_login_admin = st.form_submit_button("Masuk sebagai Admin", use_container_width=True)
                
                if btn_login_admin:
                    db_username, db_password = get_admin_credentials()
                    if admin_user == db_username and admin_pass == db_password:
                        st.session_state.user_role = "admin"
                        st.session_state.current_user_name = db_username
                        st.session_state.menu_aktif = "transaksi"
                        st.rerun()
                    else:
                        st.error("Kredensial Admin tidak valid!")


# ==========================================
# 6. HALAMAN NASABAH
# ==========================================
def halaman_nasabah():
    data = get_nasabah_detail(st.session_state.current_user_id)
    
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; color: #2E7D32;'>♻️ EcoBank</h2>", unsafe_allow_html=True)
        st.caption(f"<div style='text-align: center;'>Nasabah: <b>{st.session_state.current_user_name}</b></div>", unsafe_allow_html=True)
        st.markdown("---")
        
        if st.button("💰 Cek Saldo & Profil", use_container_width=True, type="primary" if st.session_state.menu_aktif == "cek_saldo" else "secondary"):
            st.session_state.menu_aktif = "cek_saldo"
            st.rerun()
        if st.button("📱 Tarik Tunai (QR/VA)", use_container_width=True, type="primary" if st.session_state.menu_aktif == "tarik_qr" else "secondary"):
            st.session_state.menu_aktif = "tarik_qr"
            st.rerun()
        if st.button("📜 Riwayat Transaksi", use_container_width=True, type="primary" if st.session_state.menu_aktif == "history_nasabah" else "secondary"):
            st.session_state.menu_aktif = "history_nasabah"
            st.rerun()
        if st.button("⚙️ Edit Biodata & Akun", use_container_width=True, type="primary" if st.session_state.menu_aktif == "edit_biodata" else "secondary"):
            st.session_state.menu_aktif = "edit_biodata"
            st.rerun()
            
        st.markdown("<br>" * 4, unsafe_allow_html=True)
        if st.button("🚪 Keluar Akun", use_container_width=True):
            st.session_state.user_role = None
            st.rerun()
            
    st.title("Portal Nasabah Mandiri")
    st.markdown("---")

    if st.session_state.menu_aktif == "cek_saldo":
        col_saldo, col_info = st.columns([1, 1.5])
        with col_saldo:
            st.metric(label="💰 Total Saldo Tabungan Anda", value=f"Rp {data[3]:,.0f}")
            st.info("💡 Saldo bertambah melalui penyerahan sampah fisik ke Admin.")
        with col_info:
            with st.container(border=True):
                st.markdown("### 📋 Biodata Profil")
                st.write(f"**Username:** `{st.session_state.current_user_id}`")
                st.write(f"**Nama Lengkap:** {data[0]}")
                st.write(f"**No. HP / WA:** {data[2]}")
                st.write(f"**Alamat Tinggal:** {data[1]}")

    elif st.session_state.menu_aktif == "tarik_qr":
        st.subheader("📱 Ajukan Tarik Tunai via QR Code / Virtual Account")
        st.warning("⏱️ Catatan: Batas waktu pencairan tiket QR/VA adalah maksimal 24 jam semenjak tiket dibuat.")
        
        st.markdown(f"##### Saldo Anda saat ini: **Rp {data[3]:,.0f}**")
        col_input, col_tiket = st.columns([1.2, 1.5])
        
        with col_input:
            with st.form("form_ajukan_tarik"):
                nominal_tarik = st.number_input("Masukkan Nominal Penarikan (Rp)", min_value=0, step=5000)
                submit_req = st.form_submit_button("Buat Tiket Penarikan", type="primary", use_container_width=True)
                
                if submit_req:
                    if nominal_tarik <= 0:
                        st.error("Nominal penarikan harus lebih besar dari Rp 0!")
                    elif nominal_tarik > data[3]:
                        st.error("Saldo tabungan Anda tidak mencukupi untuk melakukan penarikan ini!")
                    else:
                        token_va = simpan_pengajuan_tarik(st.session_state.current_user_id, nominal_tarik)
                        st.success(f"Tiket berhasil dibuat! Kode VA: {token_va}")
                        st.rerun()
                        
        with col_tiket:
            st.markdown("##### 🎫 Tiket Penarikan Aktif Anda (< 24 Jam)")
            df_aktif = get_pengajuan_aktif_nasabah(st.session_state.current_user_id)
            
            if df_aktif.empty:
                st.info("Tidak ada tiket penarikan aktif yang berlaku.")
            else:
                for idx, row in df_aktif.iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([1.5, 1])
                        with c1:
                            st.markdown(f"### **{row['token_va']}**")
                            st.markdown(f"Jumlah: **Rp {row['nominal']:,.0f}**")
                            st.caption(f"Dibuat: {row['waktu']}")
                        with c2:
                            qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size=150x150&data={row['token_va']}"
                            st.image(qr_url, caption="Scan me!", width=120)

    elif st.session_state.menu_aktif == "history_nasabah":
        st.subheader("📜 Riwayat Penarikan & Setoran")
        df_history = get_history(st.session_state.current_user_id)
        if df_history.empty:
            st.info("Anda belum memiliki riwayat transaksi.")
        else:
            st.dataframe(df_history, use_container_width=True, hide_index=True)

    elif st.session_state.menu_aktif == "edit_biodata":
        st.subheader("✏️ Perbarui Biodata & Password")
        with st.form("form_edit_nasabah_mandiri"):
            edit_nama = st.text_input("Nama Lengkap", value=data[0])
            edit_hp = st.text_input("Nomor HP / WhatsApp", value=data[2])
            edit_alamat = st.text_area("Alamat Lengkap", value=data[1])
            st.markdown("---")
            edit_pass = st.text_input("Password Baru", value=data[4], type="password")
            submit_edit_nasabah = st.form_submit_button("Simpan Perubahan Data", type="primary")
            
            if submit_edit_nasabah:
                if edit_nama and edit_hp and edit_alamat and edit_pass:
                    if len(edit_pass) < 6:
                        st.error("❌ Gagal! Password minimal 6 karakter.")
                    else:
                        conn = get_db_connection()
                        c = conn.cursor()
                        c.execute("UPDATE nasabah SET nama=?, alamat=?, no_hp=?, password=? WHERE username=?", 
                                  (edit_nama, edit_alamat, edit_hp, edit_pass, st.session_state.current_user_id))
                        conn.commit()
                        conn.close()
                        st.session_state.current_user_name = edit_nama
                        st.success("✅ Biodata Anda berhasil diperbarui!")
                        st.rerun()
                else:
                    st.error("Semua kolom data diri wajib diisi!")


# ==========================================
# 7. HALAMAN ADMIN
# ==========================================
def halaman_admin():
    df_nasabah = get_data_nasabah()
    
    with st.sidebar:
        st.markdown("<h2 style='text-align: center; color: #2E7D32;'>♻️ EcoBank</h2>", unsafe_allow_html=True)
        st.caption(f"<div style='text-align: center;'>Admin aktif: <b>{st.session_state.current_user_name}</b></div>", unsafe_allow_html=True)
        st.markdown("<hr style='margin-top: 10px; margin-bottom: 20px;'>", unsafe_allow_html=True)
        
        if st.button("💰 Transaksi & Kasir", use_container_width=True, type="primary" if st.session_state.menu_aktif == "transaksi" else "secondary"):
            st.session_state.menu_aktif = "transaksi"
            st.rerun()
        if st.button("📊 Direktori Data Nasabah", use_container_width=True, type="primary" if st.session_state.menu_aktif == "data" else "secondary"):
            st.session_state.menu_aktif = "data"
            st.rerun()
        if st.button("📜 Laporan Seluruh Transaksi", use_container_width=True, type="primary" if st.session_state.menu_aktif == "history_admin" else "secondary"):
            st.session_state.menu_aktif = "history_admin"
            st.rerun()
        if st.button("⚙️ Pengaturan Admin", use_container_width=True, type="primary" if st.session_state.menu_aktif == "pengaturan_admin" else "secondary"):
            st.session_state.menu_aktif = "pengaturan_admin"
            st.rerun()
        
        st.markdown("<br>" * 4, unsafe_allow_html=True)
        if st.button("🚪 Keluar Akun", use_container_width=True):
            st.session_state.user_role = None
            st.rerun()
            
    st.title("Dashboard Admin")
    m1, m2, m3 = st.columns(3)
    m1.metric(label="👥 Total Nasabah", value=f"{len(df_nasabah)} Orang")
    m2.metric(label="💰 Total Uang Beredar", value=f"Rp {df_nasabah['Saldo (Rp)'].sum() if not df_nasabah.empty else 0:,.0f}")
    m3.metric(label="🛡️ Anti-Fraud Mode", value="Aktif (Sistem Terkunci)")
    st.markdown("---")

    if st.session_state.menu_aktif == "transaksi":
        st.subheader("Kasir Operasional Secure-Gate")
        tab_qr, tab_manual = st.tabs(["🔍 Scan QR / Input Kode VA Nasabah", "✍️ Kasir Formula (Anti-Kecurangan Admin)"])
        
        with tab_qr:
            st.markdown("#### Proses Pencairan Tiket Tarik Tunai Nasabah")
            input_token = st.text_input("Scan QR Code / Masukkan Kode VA (Contoh: VA-XXXXXX)", key="input_va_admin").strip().upper()
            
            if input_token:
                conn = get_db_connection()
                c = conn.cursor()
                c.execute("SELECT username, nominal, status, waktu FROM pengajuan_tarik WHERE token_va=?", (input_token,))
                req_data = c.fetchone()
                conn.close()
                
                if req_data:
                    username_req, nominal_req, status_req, waktu_req = req_data
                    
                    waktu_buat = datetime.strptime(waktu_req, "%Y-%m-%d %H:%M:%S")
                    selisih_jam = (datetime.now() - waktu_buat).total_seconds() / 3600
                    
                    if selisih_jam > 24 and status_req == 'PENDING':
                        status_req = 'EXPIRED'
                        conn_expired = get_db_connection()
                        c_expired = conn_expired.cursor()
                        c_expired.execute("UPDATE pengajuan_tarik SET status='EXPIRED' WHERE token_va=?", (input_token,))
                        conn_expired.commit()
                        conn_expired.close()
                    
                    if status_req == 'PENDING':
                        nasabah_info = get_nasabah_detail(username_req)
                        saldo_sekarang_nasabah = nasabah_info[3]
                        
                        st.info(f"📋 **Detail Tiket Ditemukan!**\n* **Nama Nasabah:** {nasabah_info[0]} ({username_req})\n* **Nominal Penarikan:** Rp {nominal_req:,.0f}\n* **Saldo Nasabah Saat Ini:** Rp {saldo_sekarang_nasabah:,.0f}")
                        
                        if saldo_sekarang_nasabah >= nominal_req:
                            if st.button("✅ Konfirmasi Cairkan Uang Tunai", type="primary", use_container_width=True):
                                conn = get_db_connection()
                                c = conn.cursor()
                                c.execute("UPDATE nasabah SET saldo=saldo-? WHERE username=?", (nominal_req, username_req))
                                c.execute("UPDATE pengajuan_tarik SET status='SUKSES' WHERE token_va=?", (input_token,))
                                conn.commit()
                                conn.close()
                                
                                catat_transaksi(username_req, "Tarik (QR/VA)", nominal_req, f"Pencairan Token {input_token}")
                                st.success(f"🎉 Sukses mencairkan Rp {nominal_req:,.0f} untuk Nasabah {nasabah_info[0]}!")
                                st.rerun()
                        else:
                            st.error("❌ Gagal! Saldo nasabah saat ini tidak mencukupi untuk mencairkan tiket ini.")
                    elif status_req == 'EXPIRED':
                        st.error("❌ Gagal Transaksi! Tiket QR/VA ini sudah kedaluwarsa (Lebih dari 24 Jam). Nasabah harus membuat tiket baru.")
                    else:
                        st.warning(f"⚠️ Tiket ini sudah pernah dicairkan sebelumnya (**Status: {status_req}**).")
                else:
                    st.error("❌ Kode VA / Token QR tidak valid atau tidak ditemukan di sistem.")
                    
        with tab_manual:
            if df_nasabah.empty:
                st.warning("Belum ada data nasabah.")
            else:
                pilihan = st.selectbox("Pilih Nasabah Target", options=df_nasabah["Username"], format_func=lambda x: f"{x} - {df_nasabah[df_nasabah['Username'] == x]['Nama'].values[0]}")
                nasabah_detail = get_nasabah_detail(pilihan)
                saldo_now = nasabah_detail[3]
                password_asli_nasabah = nasabah_detail[4]
                
                st.success(f"💳 Saldo Saat Ini: **Rp {saldo_now:,.0f}**")
                
                col_in, col_out = st.columns(2)
                
                # --- FITUR SETOR: KUNCI FORMULA BERAT SAMPAH ---
                with col_in:
                    with st.container(border=True):
                        st.markdown("#### 📥 Setoran Sampah (Konversi Otomatis)")
                        st.caption("Admin dilarang menginput nominal Rp secara manual demi menghindari manipulasi.")
                        
                        jenis_s = st.selectbox("Pilih Jenis Sampah Fisik", options=list(HARGA_SAMPAH.keys()))
                        harga_satuan = HARGA_SAMPAH[jenis_s]
                        st.info(f"💰 Harga resmi sistem: **Rp {harga_satuan:,.0f}** / Kg atau Liter")
                        
                        berat = st.number_input("Masukkan Berat / Volume Riil (Kg/Liter)", min_value=0.0, step=0.1, format="%.2f")
                        nominal_kalkulasi = int(berat * harga_satuan)
                        
                        st.markdown(f"##### Total Saldo Masuk: **Rp {nominal_kalkulasi:,.0f}**")
                        
                        if st.button("📥 Konfirmasi & Tambah Saldo", use_container_width=True, type="primary"):
                            if nominal_kalkulasi > 0:
                                conn = get_db_connection()
                                c = conn.cursor()
                                c.execute("UPDATE nasabah SET saldo=saldo+? WHERE username=?", (nominal_kalkulasi, pilihan))
                                conn.commit()
                                conn.close()
                                
                                # Log audit mencatat jenis sampah dan berat fisiknya
                                log_audit = f"Sampah: {jenis_s}, Berat: {berat} Kg (@Rp {harga_satuan})"
                                catat_transaksi(pilihan, "Setor (Fisik)", nominal_kalkulasi, log_audit)
                                st.success("✅ Setoran sukses tercatat ke sistem!")
                                st.rerun()
                                
                # --- FITUR TARIK: WAJIB VERIFIKASI PASSWORD NASABAH ---
                with col_out:
                    with st.container(border=True):
                        st.markdown("#### 📤 Tarik Tunai Manual (Otorisasi Password)")
                        st.caption("Nasabah wajib mengetik password-nya sendiri sebagai tanda persetujuan penarikan di kasir.")
                        
                        tarik = st.number_input("Nominal Penarikan Kasir (Rp)", min_value=0, step=5000, key="tarik_manual_val")
                        
                        # Input Password Pengamanan Nasabah
                        pass_konfirmasi_nasabah = st.text_input("🔒 Masukkan Password/PIN Nasabah", type="password", help="Minta nasabah mengisi ini sendiri")
                        
                        if st.button("📤 Otorisasi & Cairkan Saldo", use_container_width=True):
                            if tarik <= 0:
                                st.error("Nominal harus lebih dari Rp 0!")
                            elif tarik > saldo_now:
                                st.error("❌ Gagal! Saldo nasabah tidak mencukupi.")
                            elif pass_konfirmasi_nasabah != password_asli_nasabah:
                                st.error("❌ Otorisasi Ditolak! Password Nasabah salah. Admin tidak bisa menarik uang secara sepihak!")
                            else:
                                conn = get_db_connection()
                                c = conn.cursor()
                                c.execute("UPDATE nasabah SET saldo=saldo-? WHERE username=?", (tarik, pilihan))
                                conn.commit()
                                conn.close()
                                
                                catat_transaksi(pilihan, "Tarik (Manual)", tarik, "Ditarik di Kasir dengan Otorisasi Pasword Nasabah")
                                st.success(f"✅ Sukses menarik Rp {tarik:,.0f}!")
                                st.rerun()

    elif st.session_state.menu_aktif == "data":
        st.subheader("Direktori Data Nasabah")
        if df_nasabah.empty:
            st.info("Sistem belum memiliki data nasabah.")
        else:
            st.dataframe(df_nasabah, use_container_width=True, hide_index=True)
            with st.expander("🛠️ Buka Panel Edit Akun & Hapus Nasabah"):
                pilihan_aksi = st.selectbox("Pilih Target Akun Nasabah", options=df_nasabah["Username"], format_func=lambda x: f"{x} - {df_nasabah[df_nasabah['Username'] == x]['Nama'].values[0]}")
                data_aksi = df_nasabah[df_nasabah["Username"] == pilihan_aksi].iloc[0]
                
                btn1, btn2 = st.columns(2)
                if btn1.button("✏️ Edit Profil & Password Nasabah", use_container_width=True):
                    pop_up_edit_admin(pilihan_aksi)
                if btn2.button("❌ Hapus Akun Permanen", use_container_width=True):
                    pop_up_hapus(pilihan_aksi, data_aksi["Nama"], data_aksi["Saldo (Rp)"])
            
            csv = df_nasabah.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Ekspor Rekap Data (CSV)", data=csv, file_name='rekap_bank_sampah.csv', mime='text/csv')

    elif st.session_state.menu_aktif == "history_admin":
        st.subheader("📊 Laporan Seluruh Transaksi & Log Audit")
        df_history_all = get_history()
        if df_history_all.empty:
            st.info("Belum ada transaksi sama sekali.")
        else:
            st.dataframe(df_history_all, use_container_width=True, hide_index=True)
            csv_history = df_history_all.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Ekspor Laporan Transaksi (CSV)", data=csv_history, file_name='history_transaksi.csv', mime='text/csv')

    elif st.session_state.menu_aktif == "pengaturan_admin":
        st.subheader("⚙️ Pengaturan Akun Keamanan Admin")
        db_username, db_password = get_admin_credentials()
        with st.form("form_edit_kredensial_admin"):
            new_admin_user = st.text_input("Username Admin Baru", value=db_username)
            new_admin_pass = st.text_input("Password Admin Baru", type="password", value=db_password)
            confirm_admin_pass = st.text_input("Konfirmasi Password Admin Baru", type="password")
            submit_admin_change = st.form_submit_button("Simpan Kredensial Admin", type="primary")
            
            if submit_admin_change:
                if not new_admin_user or not new_admin_pass:
                    st.error("Data tidak boleh kosong!")
                elif new_admin_pass != confirm_admin_pass:
                    st.error("Konfirmasi password tidak cocok!")
                else:
                    conn = get_db_connection()
                    c = conn.cursor()
                    c.execute("UPDATE admin SET username=?, password=? WHERE id=1", (new_admin_user, new_admin_pass))
                    conn.commit()
                    conn.close()
                    st.success("Kredensial admin diubah. Mengeluarkan akun...")
                    st.session_state.user_role = None
                    st.rerun()


# ==========================================
# 8. LOGIKA ROUTING UTAMA
# ==========================================
if st.session_state.user_role is None:
    halaman_auth()
elif st.session_state.user_role == "nasabah":
    halaman_nasabah()
elif st.session_state.user_role == "admin":
    halaman_admin()