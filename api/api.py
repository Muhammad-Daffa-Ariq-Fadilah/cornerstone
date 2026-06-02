"""
Cornerstone REST API v2 — melayani model klasifikasi transaksi (v2)
Coding Camp 2026 (CC26-PRU462)

Pipeline v2:
  teks -> tokenizer.texts_to_sequences -> pad_sequences(maxlen=20, post) -> float32
  amount -> RobustScaler manual: (amount - 157516.5) / 319936.0
  model.predict([text_seq, amount_scaled]) -> argmax -> label

Run lokal:
    pip install -r requirements.txt
    uvicorn api:app --reload
    -> http://127.0.0.1:8000/docs
"""

import pickle
from contextlib import asynccontextmanager
from calendar import monthrange
from datetime import date
from typing import List, Optional

import numpy as np
import pandas as pd
import tensorflow as tf
from tensorflow import keras
from tensorflow.keras.preprocessing.sequence import pad_sequences
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# =============================================================================
# CONSTANTS (di-extract dari label_encoder.pkl & scaler.pkl agar tanpa sklearn)
# =============================================================================
LABELS = ["bill", "entertainment", "food", "shopping", "transport"]  # label_encoder.classes_
MAX_LEN = 20
SCALER_CENTER = 157516.5   # RobustScaler.center_
SCALER_SCALE = 319936.0    # RobustScaler.scale_

# label model (english) -> kategori benchmark (Indonesia)
LABEL_TO_BENCHMARK_CAT = {
    "bill": "Tagihan", "entertainment": "Hiburan", "food": "Makanan & Minuman",
    "shopping": "Belanja", "transport": "Transportasi",
}

resources = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    resources["model"] = keras.models.load_model("cornerstone_model_v2.keras")
    resources["tokenizer"] = pickle.load(open("tokenizer.pkl", "rb"))
    # leakage ceiling = p90 upper_bound per kategori (robust, tidak agresif)
    b = pd.read_csv("market_benchmark_cleaned.csv")
    resources["ceiling"] = b.groupby("item_category")["upper_bound"].quantile(0.90).to_dict()
    resources["avg"] = b.groupby("item_category")["avg_price"].median().to_dict()
    yield
    resources.clear()


app = FastAPI(
    title="Cornerstone API",
    description="Klasifikasi transaksi, deteksi spending leakage, dan financial health scoring (model v2).",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# =============================================================================
# SCHEMAS
# =============================================================================
class Transaction(BaseModel):
    description: str = Field(..., examples=["netflix subscription"])
    amount: float = Field(..., gt=0, examples=[98000])


class PredictResponse(BaseModel):
    description: str
    category: str
    confidence: float


class LeakageResponse(BaseModel):
    description: str
    category: str
    amount: float
    leakage_status: str
    ratio_to_avg: float
    benchmark_avg: Optional[float]


class HealthRequest(BaseModel):
    income: float = Field(..., gt=0, examples=[4500000])
    transactions: List[Transaction]


class HealthResponse(BaseModel):
    health_score: float
    total_spending: float
    remaining_now: float
    projected_end_of_month: float
    status: str


class AnalyzeResponse(BaseModel):
    health: HealthResponse
    transactions: List[LeakageResponse]


# =============================================================================
# CORE
# =============================================================================
def _classify(description: str, amount: float):
    seq = resources["tokenizer"].texts_to_sequences([str(description)])
    seq = pad_sequences(seq, maxlen=MAX_LEN, padding="post").astype("float32")
    amt = np.array([[(float(amount) - SCALER_CENTER) / SCALER_SCALE]], dtype="float32")
    probs = resources["model"].predict([seq, amt], verbose=0)[0]
    idx = int(np.argmax(probs))
    return LABELS[idx], float(probs[idx])


def _leakage(category: str, amount: float):
    cat_id = LABEL_TO_BENCHMARK_CAT.get(category)
    ceil = resources["ceiling"].get(cat_id)
    avg = resources["avg"].get(cat_id)
    if ceil is None:
        return "unknown", 0.0, None
    ratio = amount / avg if avg else 0.0
    if amount <= ceil:
        status = "normal"
    elif amount <= 2 * ceil:
        status = "high"
    else:
        status = "extreme"
    return status, ratio, avg


def _health_score(income, total):
    if income <= 0:
        return 0.0
    return max(0.0, min(100.0, 100.0 * (1.0 - total / income)))


def _project(income, total):
    today = date.today()
    dom = today.day
    dim = monthrange(today.year, today.month)[1]
    if dom < 7:  # awal bulan: ekstrapolasi tidak reliable
        return income - total
    return income - (total + (total / dom) * (dim - dom))


def _status_text(score):
    return "sehat" if score >= 60 else ("cukup" if score >= 30 else "perlu perhatian")


# =============================================================================
# ENDPOINTS
# =============================================================================
@app.get("/")
def root():
    return {"service": "Cornerstone API", "version": "2.0.0", "status": "online", "docs": "/docs"}


@app.get("/health")
def healthcheck():
    return {"status": "ok", "model_loaded": "model" in resources}


@app.post("/predict", response_model=PredictResponse)
def predict(tx: Transaction):
    category, conf = _classify(tx.description, tx.amount)
    return PredictResponse(description=tx.description, category=category, confidence=round(conf, 4))


@app.post("/leakage", response_model=LeakageResponse)
def leakage(tx: Transaction):
    category, _ = _classify(tx.description, tx.amount)
    status, ratio, avg = _leakage(category, tx.amount)
    return LeakageResponse(
        description=tx.description, category=category, amount=tx.amount,
        leakage_status=status, ratio_to_avg=round(ratio, 2),
        benchmark_avg=round(avg, 0) if avg else None,
    )


@app.post("/health-score", response_model=HealthResponse)
def health_score(req: HealthRequest):
    total = sum(t.amount for t in req.transactions)
    score = _health_score(req.income, total)
    return HealthResponse(
        health_score=round(score, 1), total_spending=total,
        remaining_now=req.income - total,
        projected_end_of_month=round(_project(req.income, total), 0), status=_status_text(score),
    )


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(req: HealthRequest):
    rows, total = [], 0.0
    for t in req.transactions:
        category, _ = _classify(t.description, t.amount)
        status, ratio, avg = _leakage(category, t.amount)
        total += t.amount
        rows.append(LeakageResponse(
            description=t.description, category=category, amount=t.amount,
            leakage_status=status, ratio_to_avg=round(ratio, 2),
            benchmark_avg=round(avg, 0) if avg else None,
        ))
    score = _health_score(req.income, total)
    health = HealthResponse(
        health_score=round(score, 1), total_spending=total,
        remaining_now=req.income - total,
        projected_end_of_month=round(_project(req.income, total), 0), status=_status_text(score),
    )
    return AnalyzeResponse(health=health, transactions=rows)
