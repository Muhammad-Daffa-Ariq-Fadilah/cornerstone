"""
Cornerstone — Streamlit Dashboard (Integrated with real trained model)
Auditor keuangan personal berbasis AI — Coding Camp 2026 (CC26-PRU462)

Run:
    pip install -r requirements.txt
    streamlit run streamlit_app.py

Required files in same folder:
    - cornerstone_model.keras           (trained model, multi-input)
    - cornerstone_preprocessing.py      (text cleaning module)
    - benchmark_clean_final.csv         (market benchmark)
"""

import json
from datetime import date
from calendar import monthrange

import numpy as np
import pandas as pd
import streamlit as st
import tensorflow as tf
from tensorflow import keras
import plotly.graph_objects as go

from cornerstone_preprocessing import clean_transaction_name

st.set_page_config(page_title="Cornerstone", page_icon="💰", layout="wide")

# =============================================================================
# CONSTANTS
# =============================================================================
# Model output index -> category label.
# IMPORTANT: derived from training data category_encoded, NOT from the
# (incorrect) label list in cornerstone_v2_core_engine.py.
MODEL_LABELS = {0: "Bills", 1: "Entertainment", 2: "Food & Beverage", 3: "Shopping", 4: "Transport"}

# Bridge: model's English label -> benchmark's Indonesian category
LABEL_TO_BENCHMARK_CAT = {
    "Bills": "Tagihan",
    "Entertainment": "Hiburan",
    "Food & Beverage": "Makanan & Minuman",
    "Shopping": "Belanja",
    "Transport": "Transport",
}

# Friendly Indonesian display names for the model labels
LABEL_DISPLAY = {
    "Bills": "Tagihan",
    "Entertainment": "Hiburan",
    "Food & Beverage": "Makanan & Minuman",
    "Shopping": "Belanja",
    "Transport": "Transportasi",
}


# =============================================================================
# LOADERS (cached)
# =============================================================================
@st.cache_resource
def load_model():
    return keras.models.load_model("cornerstone_model.keras")


@st.cache_data
def load_benchmark():
    """
    Load item-level benchmark, aggregate to CATEGORY level using percentiles
    (robust against outliers like big electronics purchases).
    Returns dict: {benchmark_category: {min, avg, max}}
    """
    df = pd.read_csv("benchmark_clean_final.csv")
    # column: item_category, avg_price
    agg = df.groupby("item_category")["avg_price"].agg(
        price_min=lambda s: float(s.quantile(0.10)),
        price_avg=lambda s: float(s.median()),
        price_max=lambda s: float(s.quantile(0.90)),
    )
    return {cat: row.to_dict() for cat, row in agg.iterrows()}


# =============================================================================
# INFERENCE
# =============================================================================
def classify_transaction(model, raw_text, amount):
    """
    Clean text (CRITICAL — model trained on cleaned text), then predict.
    Returns (label, confidence, cleaned_text).
    """
    cleaned = clean_transaction_name(raw_text)
    text_input = tf.constant([cleaned], dtype=tf.string)
    amount_input = tf.constant([[float(amount)]], dtype=tf.float32)
    probs = model.predict(
        {"transaction_text": text_input, "amount": amount_input}, verbose=0
    )[0]
    idx = int(np.argmax(probs))
    return MODEL_LABELS[idx], float(probs[idx]), cleaned


# =============================================================================
# BUSINESS LOGIC
# =============================================================================
def detect_leakage(label, amount, benchmark):
    """
    Compare amount against category benchmark.
    Returns (status, ratio_to_avg).
    """
    bench_cat = LABEL_TO_BENCHMARK_CAT.get(label)
    if bench_cat is None or bench_cat not in benchmark:
        return "unknown", 0.0
    b = benchmark[bench_cat]
    ratio = amount / b["price_avg"] if b["price_avg"] else 0.0
    if amount <= b["price_max"]:
        return "normal", ratio
    if amount <= 2 * b["price_max"]:
        return "high", ratio
    return "extreme", ratio


def compute_health_score(income, total_spending):
    """Financial Health Score 0-100 (income-based, per original plan)."""
    if income <= 0:
        return 0.0
    ratio = total_spending / income
    return max(0.0, min(100.0, 100.0 * (1.0 - ratio)))


def project_end_of_month(income, total_spending, today):
    """Linear projection of end-of-month remaining balance."""
    days_in_month = monthrange(today.year, today.month)[1]
    dom = today.day
    if dom == 0:
        return income - total_spending
    avg_daily = total_spending / dom
    projected = total_spending + avg_daily * (days_in_month - dom)
    return income - projected


# =============================================================================
# SESSION STATE
# =============================================================================
if "transactions" not in st.session_state:
    st.session_state.transactions = []
if "income" not in st.session_state:
    st.session_state.income = 5_000_000

model = load_model()
benchmark = load_benchmark()


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
    st.caption(f"📅 {date.today().strftime('%d %B %Y')}")
    if st.button("🗑️ Reset transaksi"):
        st.session_state.transactions = []
        st.rerun()
    st.divider()
    st.caption("ℹ️ Data tidak disimpan ke database. Hilang otomatis saat halaman di-refresh (stateless).")


# =============================================================================
# HEADER
# =============================================================================
st.title("💰 Cornerstone")
st.markdown("**Auditor keuangan personal berbasis AI** — mendeteksi apakah pengeluaranmu efisien, bukan sekadar mencatat.")
st.caption("Coding Camp 2026 powered by DBS Foundation • CC26-PRU462")


# =============================================================================
# INPUT — manual + CSV upload
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
            label, conf, cleaned = classify_transaction(model, desc, amt)
            status, ratio = detect_leakage(label, amt, benchmark)
            st.session_state.transactions.append({
                "description": desc, "cleaned": cleaned, "category": label,
                "amount": amt, "confidence": conf,
                "leakage_status": status, "leakage_ratio": ratio,
            })
            st.success(f"Ditambahkan → **{LABEL_DISPLAY[label]}** ({conf*100:.1f}% confidence)")
        else:
            st.error("Deskripsi & jumlah wajib diisi.")

with tab_csv:
    st.caption("Format CSV: kolom `description` dan `amount`.")
    # Downloadable template
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
                with st.spinner("Mengklasifikasi transaksi..."):
                    for _, row in up_df.iterrows():
                        label, conf, cleaned = classify_transaction(model, row["description"], row["amount"])
                        status, ratio = detect_leakage(label, float(row["amount"]), benchmark)
                        st.session_state.transactions.append({
                            "description": row["description"], "cleaned": cleaned,
                            "category": label, "amount": float(row["amount"]),
                            "confidence": conf, "leakage_status": status, "leakage_ratio": ratio,
                        })
                st.success(f"{len(up_df)} transaksi diproses.")
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
projected = project_end_of_month(income, total_spending, date.today())

# --- Metrics ---
m1, m2, m3, m4 = st.columns(4)
m1.metric("Pemasukan", f"Rp {income:,.0f}")
m2.metric("Total Pengeluaran", f"Rp {total_spending:,.0f}")
m3.metric("Sisa Saat Ini", f"Rp {income - total_spending:,.0f}")
m4.metric("Proyeksi Akhir Bulan", f"Rp {projected:,.0f}",
          delta="⚠️ Defisit" if projected < 0 else "Aman",
          delta_color="inverse" if projected < 0 else "normal")

st.divider()

# --- Health gauge + category pie ---
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
    df["category_display"] = df["category"].map(LABEL_DISPLAY)
    breakdown = df.groupby("category_display")["amount"].sum().reset_index()
    pie = go.Figure(go.Pie(labels=breakdown["category_display"],
                           values=breakdown["amount"], hole=0.45))
    pie.update_layout(height=300, margin=dict(t=40, b=10, l=20, r=20))
    st.plotly_chart(pie, use_container_width=True)

st.divider()

# --- Spending Leakage ---
st.subheader("⚠️ Spending Leakage Detection")
leaks = df[df["leakage_status"].isin(["high", "extreme"])]
if len(leaks) > 0:
    for _, r in leaks.iterrows():
        icon = "🔴" if r["leakage_status"] == "extreme" else "🟡"
        sev = "EXTREME OVERPRICED" if r["leakage_status"] == "extreme" else "HIGH"
        st.warning(f"{icon} **{sev}** — `{r['description']}` (Rp {r['amount']:,.0f}) "
                   f"≈ **{r['leakage_ratio']:.1f}x** rata-rata kategori {LABEL_DISPLAY[r['category']]}.")
else:
    st.success("✅ Tidak ada spending leakage terdeteksi.")

st.divider()

# --- Transactions table ---
st.subheader("📝 Riwayat Transaksi")
show = df.copy()
show["category_display"] = show["category"].map(LABEL_DISPLAY)
show["amount"] = show["amount"].apply(lambda x: f"Rp {x:,.0f}")
show["confidence"] = show["confidence"].apply(lambda x: f"{x*100:.0f}%")
show = show[["description", "category_display", "amount", "confidence", "leakage_status"]]
show.columns = ["Deskripsi", "Kategori (AI)", "Jumlah", "Confidence", "Leakage"]
st.dataframe(show, use_container_width=True, hide_index=True)

st.caption("🤖 Klasifikasi oleh model Deep Learning (TensorFlow, 94.68% akurasi test). "
           "Health Score & Predictive Insight berbasis rule/matematis.")
