"""
Cornerstone — Streamlit Frontend (thin client)
Memanggil Cornerstone API via HTTP. TIDAK load model lokal.

Run:
    pip install -r requirements.txt
    streamlit run streamlit_app.py

Set API URL via sidebar, atau edit DEFAULT_API_URL di bawah.
"""

from datetime import date
from calendar import monthrange

import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# Ganti dengan URL API kamu setelah deploy (mis. HF Space)
DEFAULT_API_URL = "https://your-username-cornerstone-api.hf.space"

LABEL_DISPLAY = {
    "Bills": "Tagihan", "Entertainment": "Hiburan", "Food & Beverage": "Makanan & Minuman",
    "Shopping": "Belanja", "Transport": "Transportasi",
}

st.set_page_config(page_title="Cornerstone", page_icon="💰", layout="wide")


# =============================================================================
# API CLIENT
# =============================================================================
def call_api(base_url, endpoint, payload, timeout=60):
    """
    POST ke API dengan error handling.
    Returns (data, error_message). Salah satu None.
    """
    try:
        resp = requests.post(f"{base_url.rstrip('/')}{endpoint}",
                             json=payload, timeout=timeout)
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"API error {resp.status_code}: {resp.text[:200]}"
    except requests.exceptions.Timeout:
        return None, "API timeout. Kalau pakai free tier (HF Spaces), API mungkin lagi 'bangun' dari sleep — coba lagi dalam ~30 detik."
    except requests.exceptions.ConnectionError:
        return None, "Tidak bisa connect ke API. Cek URL-nya bener & API-nya running."
    except Exception as e:
        return None, f"Error: {e}"


def check_api(base_url):
    """Ping /health. Returns True if reachable."""
    try:
        resp = requests.get(f"{base_url.rstrip('/')}/health", timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


# =============================================================================
# LOCAL MATH (no model needed — pure arithmetic)
# =============================================================================
def compute_health_score(income, total_spending):
    if income <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (1.0 - total_spending / income)))


def project_eom(income, total_spending):
    today = date.today()
    dom = today.day
    days_in_month = monthrange(today.year, today.month)[1]
    if dom == 0:
        return income - total_spending
    avg_daily = total_spending / dom
    return income - (total_spending + avg_daily * (days_in_month - dom))


# =============================================================================
# SESSION STATE
# =============================================================================
if "transactions" not in st.session_state:
    st.session_state.transactions = []
if "income" not in st.session_state:
    st.session_state.income = 5_000_000
if "api_url" not in st.session_state:
    st.session_state.api_url = DEFAULT_API_URL


# =============================================================================
# SIDEBAR
# =============================================================================
with st.sidebar:
    st.header("👤 Profil")
    st.session_state.income = st.number_input(
        "Pemasukan bulanan (Rp)", min_value=0,
        value=st.session_state.income, step=500_000,
    )
    st.divider()
    st.subheader("🔌 Koneksi API")
    st.session_state.api_url = st.text_input("API URL", value=st.session_state.api_url)
    if st.button("Cek koneksi"):
        if check_api(st.session_state.api_url):
            st.success("API terhubung ✓")
        else:
            st.error("API tidak terjangkau. Cek URL / status Space.")
    st.divider()
    st.caption(f"📅 {date.today().strftime('%d %B %Y')}")
    if st.button("🗑️ Reset transaksi"):
        st.session_state.transactions = []
        st.rerun()
    st.divider()
    st.caption("ℹ️ Data tidak disimpan ke database (stateless).")


# =============================================================================
# HEADER
# =============================================================================
st.title("💰 Cornerstone")
st.markdown("**Auditor keuangan personal berbasis AI** — mendeteksi apakah pengeluaranmu efisien.")
st.caption("Coding Camp 2026 powered by DBS Foundation • CC26-PRU462")


# =============================================================================
# INPUT
# =============================================================================
tab_manual, tab_csv = st.tabs(["➕ Input Manual", "📁 Upload CSV"])

with tab_manual:
    with st.form("add_tx", clear_on_submit=True):
        c1, c2, c3 = st.columns([3, 2, 1])
        with c1:
            desc = st.text_input("Deskripsi transaksi",
                                 placeholder="contoh: N3TFL1X*SUBSCRIPTION, gofood mcd, bayar pln")
        with c2:
            amt = st.number_input("Jumlah (Rp)", min_value=0, value=0, step=1_000)
        with c3:
            st.write(""); st.write("")
            submitted = st.form_submit_button("Tambah", type="primary")
    if submitted:
        if desc and amt > 0:
            with st.spinner("Mengklasifikasi via API..."):
                data, err = call_api(st.session_state.api_url, "/leakage",
                                     {"description": desc, "amount": amt})
            if err:
                st.error(err)
            else:
                st.session_state.transactions.append({
                    "description": desc, "category": data["category"],
                    "amount": amt, "leakage_status": data["leakage_status"],
                    "leakage_ratio": data["ratio_to_avg"],
                })
                st.success(f"Ditambahkan → **{LABEL_DISPLAY.get(data['category'], data['category'])}**")
        else:
            st.error("Deskripsi & jumlah wajib diisi.")

with tab_csv:
    st.caption("Format CSV: kolom `description` dan `amount`.")
    template = pd.DataFrame({
        "description": ["N3TFL1X*SUBSCRIPTION - <ID>", "GOFOOD MCDONALDS", "TAGIHAN LISTRIK PLN"],
        "amount": [98000, 55000, 350000],
    })
    st.download_button("⬇️ Download template CSV",
                       template.to_csv(index=False), "cornerstone_template.csv", "text/csv")
    uploaded = st.file_uploader("Upload CSV transaksi", type="csv")
    if uploaded is not None:
        try:
            up_df = pd.read_csv(uploaded)
            if "description" not in up_df.columns or "amount" not in up_df.columns:
                st.error("CSV harus punya kolom 'description' dan 'amount'.")
            else:
                # Kirim batch ke /analyze (1 call untuk semua)
                payload = {
                    "income": float(st.session_state.income),
                    "transactions": [
                        {"description": str(r["description"]), "amount": float(r["amount"])}
                        for _, r in up_df.iterrows()
                    ],
                }
                with st.spinner("Memproses batch via API..."):
                    data, err = call_api(st.session_state.api_url, "/analyze", payload, timeout=120)
                if err:
                    st.error(err)
                else:
                    for t in data["transactions"]:
                        st.session_state.transactions.append({
                            "description": t["description"], "category": t["category"],
                            "amount": t["amount"], "leakage_status": t["leakage_status"],
                            "leakage_ratio": t["ratio_to_avg"],
                        })
                    st.success(f"{len(data['transactions'])} transaksi diproses.")
        except Exception as e:
            st.error(f"Gagal baca CSV: {e}")

st.divider()


# =============================================================================
# DASHBOARD
# =============================================================================
if not st.session_state.transactions:
    st.info("👆 Belum ada transaksi. Tambah manual atau upload CSV untuk melihat analisis.")
    st.stop()

df = pd.DataFrame(st.session_state.transactions)
total_spending = float(df["amount"].sum())
income = float(st.session_state.income)
health = compute_health_score(income, total_spending)
projected = project_eom(income, total_spending)

m1, m2, m3, m4 = st.columns(4)
m1.metric("Pemasukan", f"Rp {income:,.0f}")
m2.metric("Total Pengeluaran", f"Rp {total_spending:,.0f}")
m3.metric("Sisa Saat Ini", f"Rp {income - total_spending:,.0f}")
m4.metric("Proyeksi Akhir Bulan", f"Rp {projected:,.0f}",
          delta="⚠️ Defisit" if projected < 0 else "Aman",
          delta_color="inverse" if projected < 0 else "normal")

st.divider()

cga, cgb = st.columns(2)
with cga:
    st.subheader("📊 Financial Health Meter")
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
    df["category_display"] = df["category"].map(lambda c: LABEL_DISPLAY.get(c, c))
    breakdown = df.groupby("category_display")["amount"].sum().reset_index()
    pie = go.Figure(go.Pie(labels=breakdown["category_display"],
                           values=breakdown["amount"], hole=0.45))
    pie.update_layout(height=300, margin=dict(t=40, b=10, l=20, r=20))
    st.plotly_chart(pie, use_container_width=True)

st.divider()

st.subheader("⚠️ Spending Leakage Detection")
leaks = df[df["leakage_status"].isin(["high", "extreme"])]
if len(leaks) > 0:
    for _, r in leaks.iterrows():
        icon = "🔴" if r["leakage_status"] == "extreme" else "🟡"
        sev = "EXTREME OVERPRICED" if r["leakage_status"] == "extreme" else "HIGH"
        st.warning(f"{icon} **{sev}** — `{r['description']}` (Rp {r['amount']:,.0f}) "
                   f"≈ **{r['leakage_ratio']:.1f}x** rata-rata kategori "
                   f"{LABEL_DISPLAY.get(r['category'], r['category'])}.")
else:
    st.success("✅ Tidak ada spending leakage terdeteksi.")

st.divider()

st.subheader("📝 Riwayat Transaksi")
show = df.copy()
show["category_display"] = show["category"].map(lambda c: LABEL_DISPLAY.get(c, c))
show["amount"] = show["amount"].apply(lambda x: f"Rp {x:,.0f}")
show = show[["description", "category_display", "amount", "leakage_status"]]
show.columns = ["Deskripsi", "Kategori (AI)", "Jumlah", "Leakage"]
st.dataframe(show, use_container_width=True, hide_index=True)

st.caption("🤖 Klasifikasi via Cornerstone API (model Deep Learning TensorFlow, 94.68% akurasi). "
           "Health Score & proyeksi dihitung lokal (rule-based).")
