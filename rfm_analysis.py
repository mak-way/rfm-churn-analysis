"""RFM segmentation + cohort retention. Usage: python rfm_analysis.py [orders.csv]
CSV columns needed: customer_id, order_id, order_date, sales  (Superstore: Customer ID, Order ID, Order Date, Sales)
With no file, a synthetic Superstore-like dataset is generated so the pipeline runs end to end."""
import sys, sqlite3, numpy as np, pandas as pd
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt

SNAPSHOT = pd.Timestamp("2026-09-28")

def synthetic(n=900, seed=7):
    rng = np.random.default_rng(seed); rows = []; oid = 0
    for c in range(n):
        start = SNAPSHOT - pd.Timedelta(days=int(rng.integers(30, 1000)))
        rate = rng.gamma(2, 1.2) / 365          # orders per day
        churn = rng.random() < 0.35
        end = start + pd.Timedelta(days=int(rng.integers(60, 400))) if churn else SNAPSHOT
        end = min(end, SNAPSHOT); t = start
        while t <= end:
            oid += 1
            rows.append((f"C{c:04d}", f"O{oid:06d}", t, round(float(rng.lognormal(5, .8)), 2)))
            t += pd.Timedelta(days=max(1, int(rng.exponential(1 / rate))))
    return pd.DataFrame(rows, columns=["customer_id", "order_id", "order_date", "sales"])

def load(path):
    if not path: return synthetic()
    d = pd.read_csv(path, encoding="latin1").rename(columns={"Customer ID": "customer_id",
        "Order ID": "order_id", "Order Date": "order_date", "Sales": "sales"})
    d["order_date"] = pd.to_datetime(d["order_date"]); return d[["customer_id", "order_id", "order_date", "sales"]]

def score(s, ascending=True):  # quintile 1-5, 5 = best; rank(first) avoids qcut tie errors
    return pd.qcut(s.rank(method="first", ascending=ascending), 5, labels=[1, 2, 3, 4, 5]).astype(int)

def segment(r, f):
    if r >= 4 and f >= 4: return "Champions"
    if r <= 2 and f >= 4: return "Can't lose"
    if r <= 2 and f == 3: return "At risk"
    if r >= 3 and f >= 3: return "Loyal"
    if r >= 4 and f <= 2: return "New / promising"
    if r <= 2: return "Hibernating"
    return "Needs attention"

df = load(sys.argv[1] if len(sys.argv) > 1 else None)
df["order_date"] = pd.to_datetime(df["order_date"])

rfm = df.groupby("customer_id").agg(last=("order_date", "max"), frequency=("order_id", "nunique"),
                                    monetary=("sales", "sum")).reset_index()
rfm["recency"] = (SNAPSHOT - rfm["last"]).dt.days
rfm["R"] = score(rfm["recency"], ascending=False)   # fewer days = higher score
rfm["F"] = score(rfm["frequency"]); rfm["M"] = score(rfm["monetary"])
rfm["segment"] = [segment(r, f) for r, f in zip(rfm.R, rfm.F)]
rfm.to_csv("rfm_customers.csv", index=False)

seg = rfm.groupby("segment").agg(customers=("customer_id", "count"), avg_recency_days=("recency", "mean"),
        avg_orders=("frequency", "mean"), revenue=("monetary", "sum")).round(1)
seg["pct_customers"] = (seg.customers / seg.customers.sum() * 100).round(1)
seg["pct_revenue"] = (seg.revenue / seg.revenue.sum() * 100).round(1)
seg = seg.sort_values("revenue", ascending=False); seg.to_csv("segment_summary.csv"); print(seg, "\n")

# --- cohort retention (monthly) ---
df["order_month"] = df.order_date.dt.to_period("M")
df["cohort"] = df.groupby("customer_id").order_date.transform("min").dt.to_period("M")
df["age"] = (df.order_month - df.cohort).apply(lambda x: x.n)
coh = df.groupby(["cohort", "age"]).customer_id.nunique().unstack(fill_value=0)
ret = coh.div(coh[0], axis=0).round(3); ret.to_csv("cohort_retention.csv")
ret = ret[ret.index >= ret.index.max() - 17].iloc[:, :13]   # last 18 cohorts, 12 months

# --- charts ---
fig, ax = plt.subplots(1, 2, figsize=(14, 5))
s = seg[["pct_customers", "pct_revenue"]]; s.plot.barh(ax=ax[0], color=["#9bb", "#159"])
ax[0].set_title("Share of customers vs share of revenue by segment"); ax[0].invert_yaxis(); ax[0].set_xlabel("%")
im = ax[1].imshow(ret.values, cmap="Blues", vmin=0, vmax=.5, aspect="auto")
ax[1].set_yticks(range(len(ret))); ax[1].set_yticklabels(ret.index.astype(str), fontsize=7)
ax[1].set_xlabel("Months since first order"); ax[1].set_title("Cohort retention"); fig.colorbar(im, ax=ax[1])
plt.tight_layout(); plt.savefig("rfm_dashboard.png", dpi=130)

# --- validate SQL version against pandas ---
con = sqlite3.connect(":memory:")
o = df[["customer_id", "order_id", "order_date", "sales"]].copy(); o["order_date"] = o.order_date.dt.strftime("%Y-%m-%d")
o.to_sql("orders", con, index=False)
q = pd.read_sql(open("rfm_segments.sql").read(), con)
print("SQL segment counts:\n", q.groupby("segment").size().sort_values(ascending=False))
