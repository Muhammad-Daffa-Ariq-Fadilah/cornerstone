"""
Cornerstone — Streamlit Frontend (thin client) v2
Tambahan: tipe transaksi (Pengeluaran/Pemasukan/Transfer), frekuensi langganan,
hapus transaksi, penamaan & UX lebih ramah. Memanggil Cornerstone API via HTTP.

Run:
    pip install -r requirements.txt
    streamlit run streamlit_app.py
"""

import os

from datetime import date
from calendar import monthrange

import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

DEFAULT_API_URL = "https://noname3214-cornerstone-api.hf.space"

# Kategori AI (Pengeluaran) — display Indonesia (model v2: label lowercase)
LABEL_DISPLAY = {
    "bill": "Tagihan", "entertainment": "Hiburan", "food": "Makanan & Minuman",
    "shopping": "Belanja", "transport": "Transportasi",
}
INCOME_CATEGORIES = ["Gaji", "Bonus", "Freelance", "Hadiah", "Lainnya"]
TRANSFER_CATEGORIES = ["Tabungan", "Investasi", "Kirim ke Orang", "Lainnya"]
PERIODS = ["Sekali", "Mingguan", "Bulanan", "Tahunan"]

# Logo & favicon (taruh logo.png + icon.png di folder yang sama). Aman jika tidak ada.
_DIR = os.path.dirname(__file__)
LOGO_PATH = os.path.join(_DIR, "logo.png")
ICON_PATH = os.path.join(_DIR, "icon.png")
_page_icon = ICON_PATH if os.path.exists(ICON_PATH) else "💰"

st.set_page_config(page_title="Cornerstone", page_icon=_page_icon, layout="wide")

if os.path.exists(LOGO_PATH):
    try:
        st.logo(LOGO_PATH, size="large")
    except Exception:
        pass


# =============================================================================
# API CLIENT
# =============================================================================
def call_api(base_url, endpoint, payload, timeout=60):
    try:
        resp = requests.post(f"{base_url.rstrip('/')}{endpoint}", json=payload, timeout=timeout)
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"API error {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.Timeout:
        return None, "API timeout. Kalau pakai free tier (HF Spaces), API mungkin lagi 'bangun' dari sleep — coba lagi ~30 detik."
    except requests.exceptions.ConnectionError:
        return None, "Tidak bisa connect ke API. Cek URL & status Space."
    except Exception as e:
        return None, f"Error: {e}"


def check_api(base_url):
    try:
        return requests.get(f"{base_url.rstrip('/')}/health", timeout=10).status_code == 200
    except Exception:
        return False


# =============================================================================
# HELPERS
# =============================================================================
def monthly_equiv(amount, period):
    """Normalisasi nominal ke per-bulan untuk pengecekan leakage yang adil."""
    if period == "Mingguan":
        return amount * 4.33
    if period == "Tahunan":
        return amount / 12
    return amount  # Sekali, Bulanan


def compute_health_score(income, total_expense):
    if income <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (1.0 - total_expense / income)))


def project_eom(income, total_expense):
    today = date.today()
    dom = today.day
    dim = monthrange(today.year, today.month)[1]
    # Guard: di awal bulan (dom < 7) ekstrapolasi harian terlalu liar,
    # jadi pakai pengeluaran aktual saja (konservatif).
    if dom < 7:
        return income - total_expense
    return income - (total_expense + (total_expense / dom) * (dim - dom))


# =============================================================================
# SESSION STATE
# =============================================================================
if "transactions" not in st.session_state:
    st.session_state.transactions = []
if "base_income" not in st.session_state:
    st.session_state.base_income = 0
if "api_url" not in st.session_state:
    st.session_state.api_url = DEFAULT_API_URL
if "next_id" not in st.session_state:
    st.session_state.next_id = 1


def add_transaction(tx):
    tx["id"] = st.session_state.next_id
    st.session_state.next_id += 1
    st.session_state.transactions.append(tx)


def delete_transaction(tx_id):
    st.session_state.transactions = [t for t in st.session_state.transactions if t["id"] != tx_id]


# =============================================================================
# SIDEBAR
# =============================================================================
with st.sidebar:
    st.header("👤 Profil")
    st.session_state.base_income = st.number_input(
        "Pemasukan bulanan tetap (Rp)", min_value=0,
        value=st.session_state.base_income, step=500_000,
        help="Gaji pokok bulanan. Pemasukan tambahan bisa dicatat sebagai transaksi.",
    )
    st.divider()
    st.subheader("🔌 Koneksi API")
    st.session_state.api_url = st.text_input("API URL", value=st.session_state.api_url)
    if st.button("Cek koneksi"):
        if check_api(st.session_state.api_url):
            st.success("API terhubung ✓")
        else:
            st.error("API tidak terjangkau.")
    st.divider()
    st.caption(f"📅 {date.today().strftime('%d %B %Y')}")
    if st.button("🗑️ Reset semua transaksi"):
        st.session_state.transactions = []
        st.rerun()
    st.caption("ℹ️ Data tidak disimpan ke database (stateless).")


# =============================================================================
# HEADER
# =============================================================================
if os.path.exists(LOGO_PATH):
    st.image(LOGO_PATH, width=260)
else:
    st.title("💰 Cornerstone")
st.markdown("**Auditor keuangan personal berbasis AI** — mendeteksi apakah pengeluaranmu efisien.")
st.caption("Coding Camp 2026 powered by DBS Foundation • CC26-PRU462")


# =============================================================================
# INPUT — pilih tipe dulu, field menyesuaikan
# =============================================================================
st.subheader("➕ Catat Transaksi")
tx_type = st.radio("Tipe transaksi", ["Pengeluaran", "Pemasukan", "Transfer"], horizontal=True)

if tx_type == "Pengeluaran":
    st.caption("Pengeluaran diklasifikasi otomatis oleh AI & dicek spending leakage.")
    c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
    with c1:
        desc = st.text_input("Deskripsi", placeholder="contoh: netflix subscription, gofood mcd, bayar pln", key="exp_desc")
    with c2:
        nominal = st.number_input("Nominal (Rp)", min_value=0, value=0, step=1_000, key="exp_amt")
    with c3:
        period = st.selectbox("Frekuensi", PERIODS, key="exp_period",
                              help="Langganan tahunan/mingguan dinormalisasi ke per-bulan saat cek leakage.")
    with c4:
        st.write(""); st.write("")
        add_exp = st.button("Tambah", type="primary", key="add_exp")
    if add_exp:
        if desc and nominal > 0:
            eq = monthly_equiv(nominal, period)
            with st.spinner("Mengklasifikasi via API..."):
                data, err = call_api(st.session_state.api_url, "/leakage",
                                     {"description": desc, "amount": eq})
            if err:
                st.error(err)
            else:
                add_transaction({
                    "type": "Pengeluaran", "description": desc, "amount": nominal,
                    "period": period, "category": data["category"],
                    "leakage_status": data["leakage_status"], "leakage_ratio": data["ratio_to_avg"],
                })
                st.rerun()
        else:
            st.error("Deskripsi & nominal wajib diisi.")

elif tx_type == "Pemasukan":
    st.caption("Pemasukan menambah total income — tidak melewati AI.")
    c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
    with c1:
        desc = st.text_input("Deskripsi", placeholder="contoh: gaji bulan Mei", key="inc_desc")
    with c2:
        nominal = st.number_input("Nominal (Rp)", min_value=0, value=0, step=100_000, key="inc_amt")
    with c3:
        sub = st.selectbox("Kategori", INCOME_CATEGORIES, key="inc_cat")
    with c4:
        st.write(""); st.write("")
        add_inc = st.button("Tambah", type="primary", key="add_inc")
    if add_inc:
        if nominal > 0:
            add_transaction({
                "type": "Pemasukan", "description": desc or sub, "amount": nominal,
                "period": "Sekali", "category": sub, "leakage_status": "-", "leakage_ratio": 0,
            })
            st.rerun()
        else:
            st.error("Nominal wajib diisi.")

else:  # Transfer
    st.caption("Transfer dicatat terpisah — tidak dihitung sebagai pengeluaran konsumsi.")
    c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
    with c1:
        desc = st.text_input("Deskripsi", placeholder="contoh: transfer ke tabungan", key="trf_desc")
    with c2:
        nominal = st.number_input("Nominal (Rp)", min_value=0, value=0, step=100_000, key="trf_amt")
    with c3:
        sub = st.selectbox("Tujuan", TRANSFER_CATEGORIES, key="trf_cat")
    with c4:
        st.write(""); st.write("")
        add_trf = st.button("Tambah", type="primary", key="add_trf")
    if add_trf:
        if nominal > 0:
            add_transaction({
                "type": "Transfer", "description": desc or sub, "amount": nominal,
                "period": "Sekali", "category": sub, "leakage_status": "-", "leakage_ratio": 0,
            })
            st.rerun()
        else:
            st.error("Nominal wajib diisi.")

# --- CSV bulk upload (semua baris diperlakukan sebagai Pengeluaran) ---
with st.expander("📁 Upload CSV (bulk pengeluaran)"):
    st.caption("Format CSV: kolom `description`, `amount`, dan opsional `period` "
               "(Sekali/Mingguan/Bulanan/Tahunan — kosong = Sekali). Semua baris dicatat sebagai Pengeluaran.")
    template = pd.DataFrame({
        "description": ["NETFLIX*SUBSCRIPTION", "GOFOOD MCDONALDS", "TAGIHAN LISTRIK PLN"],
        "amount": [1200000, 55000, 350000],
        "period": ["Tahunan", "Sekali", "Bulanan"],
    })
    st.download_button("⬇️ Download template CSV", template.to_csv(index=False),
                       "cornerstone_template.csv", "text/csv")
    uploaded = st.file_uploader("Upload CSV transaksi", type="csv")
    if uploaded is None:
        st.session_state.last_upload_sig = None
    else:
        sig = (uploaded.name, uploaded.size)
        if st.session_state.get("last_upload_sig") == sig:
            st.info("File ini sudah diproses. Hapus file di atas, lalu upload lagi untuk memproses ulang.")
        else:
            try:
                up_df = pd.read_csv(uploaded)
                if "description" not in up_df.columns or "amount" not in up_df.columns:
                    st.error("CSV harus punya kolom 'description' dan 'amount'.")
                else:
                    has_period = "period" in up_df.columns
                    parsed = []
                    for _, r in up_df.iterrows():
                        p = "Sekali"
                        if has_period and pd.notna(r.get("period")):
                            cand = str(r["period"]).strip().capitalize()
                            if cand in PERIODS:
                                p = cand
                        parsed.append({"description": str(r["description"]),
                                       "amount": float(r["amount"]), "period": p})
                    payload = {"income": float(st.session_state.base_income),
                               "transactions": [{"description": x["description"],
                                                 "amount": monthly_equiv(x["amount"], x["period"])}
                                                for x in parsed]}
                    with st.spinner("Memproses batch via API..."):
                        data, err = call_api(st.session_state.api_url, "/analyze", payload, timeout=120)
                    if err:
                        st.error(err)
                    else:
                        for x, t in zip(parsed, data["transactions"]):
                            add_transaction({
                                "type": "Pengeluaran", "description": x["description"], "amount": x["amount"],
                                "period": x["period"], "category": t["category"],
                                "leakage_status": t["leakage_status"], "leakage_ratio": t["ratio_to_avg"],
                            })
                        st.session_state.last_upload_sig = sig
                        st.success(f"{len(parsed)} transaksi ditambahkan.")
            except Exception as e:
                st.error(f"Gagal baca CSV: {e}")

st.divider()


# =============================================================================
# DASHBOARD
# =============================================================================
txs = st.session_state.transactions
if not txs:
    st.info("👆 Belum ada transaksi. Catat Pengeluaran, Pemasukan, atau Transfer di atas.")
    st.stop()

df = pd.DataFrame(txs)
expenses = df[df["type"] == "Pengeluaran"]
incomes = df[df["type"] == "Pemasukan"]
transfers = df[df["type"] == "Transfer"]

total_expense = float(expenses["amount"].sum()) if len(expenses) else 0.0
total_income = float(st.session_state.base_income) + (float(incomes["amount"].sum()) if len(incomes) else 0.0)
total_transfer = float(transfers["amount"].sum()) if len(transfers) else 0.0
health = compute_health_score(total_income, total_expense)
projected = project_eom(total_income, total_expense)

# --- Metrics ---
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Pemasukan", f"Rp {total_income:,.0f}")
m2.metric("Total Pengeluaran", f"Rp {total_expense:,.0f}")
m3.metric("Sisa Saat Ini", f"Rp {total_income - total_expense:,.0f}")
m4.metric("Proyeksi Akhir Bulan", f"Rp {projected:,.0f}",
          delta="⚠️ Defisit" if projected < 0 else "Aman",
          delta_color="inverse" if projected < 0 else "normal")
if total_transfer > 0:
    st.caption(f"💸 Total transfer (tidak dihitung sebagai konsumsi): Rp {total_transfer:,.0f}")

st.divider()

# --- Health + pie (expense only) ---
cga, cgb = st.columns(2)
with cga:
    st.subheader("📊 Financial Health Meter")
    if total_income <= 0:
        st.info("Isi **Pemasukan bulanan** di sidebar untuk melihat Health Score.")
    else:
        gauge = go.Figure(go.Indicator(
            mode="gauge+number", value=health,
            domain={"x": [0, 1], "y": [0, 1]}, title={"text": "Health Score"},
            gauge={"axis": {"range": [0, 100], "tickvals": [0, 25, 50, 75, 100]},
                   "bar": {"color": "#2c3e50"},
                   "steps": [{"range": [0, 30], "color": "#ffcccc"},
                             {"range": [30, 60], "color": "#fff3b0"},
                             {"range": [60, 100], "color": "#c6f6c4"}]},
        ))
        gauge.update_layout(height=300, margin=dict(t=40, b=20, l=50, r=50))
        st.plotly_chart(gauge, use_container_width=True)
        if health >= 60:
            st.success("Keuangan sehat. Pertahankan!")
        elif health >= 30:
            st.warning("Cukup, tapi perlu evaluasi.")
        else:
            st.error("Butuh perhatian serius.")

with cgb:
    st.subheader("📈 Pengeluaran per Kategori")
    if len(expenses):
        exp = expenses.copy()
        exp["cat_display"] = exp["category"].map(lambda c: LABEL_DISPLAY.get(c, c))
        bd = exp.groupby("cat_display")["amount"].sum().reset_index()
        pie = go.Figure(go.Pie(labels=bd["cat_display"], values=bd["amount"], hole=0.45))
        pie.update_layout(height=300, margin=dict(t=40, b=10, l=20, r=20))
        st.plotly_chart(pie, use_container_width=True)
    else:
        st.info("Belum ada pengeluaran untuk divisualisasi.")

st.divider()

# --- Leakage (expense only) ---
st.subheader("⚠️ Spending Leakage Detection")
leaks = expenses[expenses["leakage_status"].isin(["high", "extreme"])] if len(expenses) else expenses
if len(leaks) > 0:
    for _, r in leaks.iterrows():
        icon = "🔴" if r["leakage_status"] == "extreme" else "🟡"
        sev = "EXTREME OVERPRICED" if r["leakage_status"] == "extreme" else "HIGH"
        deg = "jauh melebihi" if r["leakage_status"] == "extreme" else "melebihi"
        per = f" ({r['period']})" if r["period"] != "Sekali" else ""
        st.warning(f"{icon} **{sev}** — `{r['description']}`{per} (Rp {r['amount']:,.0f}) "
                   f"{deg} rentang harga wajar kategori {LABEL_DISPLAY.get(r['category'], r['category'])}.")
else:
    st.success("✅ Tidak ada spending leakage terdeteksi.")

st.divider()

# --- History with filter, scroll, delete, download ---
st.subheader("📝 Riwayat Transaksi")

# Filter controls
fc1, fc2, fc3 = st.columns([2, 2, 2])
with fc1:
    f_type = st.selectbox("Filter tipe", ["Semua", "Pengeluaran", "Pemasukan", "Transfer"])
with fc2:
    cats_present = sorted({(LABEL_DISPLAY.get(t["category"], t["category"]) if t["type"] == "Pengeluaran" else t["category"]) for t in txs})
    f_cat = st.selectbox("Filter kategori", ["Semua"] + cats_present)

def cat_display(t):
    return LABEL_DISPLAY.get(t["category"], t["category"]) if t["type"] == "Pengeluaran" else t["category"]

filtered = [t for t in txs
            if (f_type == "Semua" or t["type"] == f_type)
            and (f_cat == "Semua" or cat_display(t) == f_cat)]

# Download (full history, unfiltered)
dl_df = pd.DataFrame([{
    "Tipe": t["type"], "Deskripsi": t["description"], "Kategori": cat_display(t),
    "Frekuensi": t["period"], "Nominal": t["amount"], "Leakage": t["leakage_status"],
} for t in txs])
with fc3:
    st.write(""); st.write("")
    st.download_button("⬇️ Download riwayat (CSV)", dl_df.to_csv(index=False),
                       "riwayat_cornerstone.csv", "text/csv")

st.caption(f"Menampilkan {len(filtered)} dari {len(txs)} transaksi. Klik 🗑️ untuk hapus.")

# Scrollable container (tinggi tetap walau banyak transaksi)
with st.container(height=360):
    h = st.columns([1.2, 3, 2, 2, 1.5, 0.8])
    for col, txt in zip(h, ["Tipe", "Deskripsi", "Kategori", "Nominal", "Leakage", ""]):
        col.markdown(f"**{txt}**")
    for t in filtered:
        row = st.columns([1.2, 3, 2, 2, 1.5, 0.8])
        row[0].write(t["type"])
        desc_txt = t["description"]
        if t["type"] == "Pengeluaran" and t["period"] != "Sekali":
            desc_txt += f" ({t['period']})"
        row[1].write(desc_txt)
        row[2].write(cat_display(t))
        row[3].write(f"Rp {t['amount']:,.0f}")
        row[4].write(t["leakage_status"])
        if row[5].button("🗑️", key=f"del_{t['id']}"):
            delete_transaction(t["id"])
            st.rerun()

st.caption("🤖 Pengeluaran diklasifikasi via Cornerstone API (model Deep Learning, akurasi 99.84%). "
           "Pemasukan & Transfer dicatat manual; Health Score & proyeksi dihitung lokal.")
