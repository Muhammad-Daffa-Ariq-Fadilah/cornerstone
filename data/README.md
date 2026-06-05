# Data

Kumpulan dataset untuk pelatihan model, benchmark harga, dan evaluasi.
Proses pengumpulan, pembersihan, dan integrasi data didokumentasikan di folder `notebook/`.

| File | Baris | Kolom | Keterangan |
|---|---|---|---|
| `sumber - Sheet1.csv` | 59 | No, Item, Termurah (Rp), Rata-rata (Rp), Termahal (Rp) | Data sumber harga acuan (mentah, hasil riset pasar) |
| `market_benchmark_dataset.csv` | 2.250 | item_category, item_name, avg_price, lower_bound, upper_bound | Benchmark harga pasar hasil olahan untuk deteksi spending leakage |
| `financial_transaction_train.csv` | 10.000 | Transaction_Text, Label | Data latih klasifikasi transaksi |
| `financial_transaction_test.csv` | 1.000 | Transaction_Text, Label | Data uji klasifikasi transaksi |
| `public_transactions_test.csv` | 1.220 | transaction_name, amount, category, category_encoded | Test set evaluasi performa model |

> Catatan: pemetaan label kategori final mengacu pada `label_encoder` di pipeline model.
