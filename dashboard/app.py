import sys
from pathlib import Path

import altair as alt
import duckdb
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lendlake.config import Settings  # noqa: E402

BUCKET_COLORS = ["#2f7d5b", "#e0b33a", "#e07b39", "#c8553d", "#8c2f39"]

st.set_page_config(page_title="LendLake portfolio", layout="wide")


@st.cache_data(ttl=300)
def query(sql: str) -> pd.DataFrame:
    with duckdb.connect(str(Settings.from_env().duckdb_path), read_only=True) as con:
        return con.execute(sql).df()


def crore(value: float) -> str:
    return f"₹{value / 1e7:,.1f} Cr"


def pct(numerator: float, denominator: float) -> str:
    return f"{numerator / denominator:.1%}" if denominator else "n/a"


summary = query("select * from gold.mart_portfolio_summary")
if summary.empty:
    st.warning("No gold data yet. Run the pipeline first: python -m lendlake run ...")
    st.stop()

months = sorted(summary["snapshot_month"].unique(), reverse=True)
with st.sidebar:
    st.header("Filters")
    month = st.selectbox("As of month", months, format_func=lambda d: pd.Timestamp(d).strftime("%b %Y"))
    products = st.multiselect("Product", sorted(summary["product_code"].unique()))
    regions = st.multiselect("Region", sorted(summary["region"].unique()))


def filtered(df: pd.DataFrame) -> pd.DataFrame:
    if products and "product_code" in df:
        df = df[df["product_code"].isin(products)]
    if regions and "region" in df:
        df = df[df["region"].isin(regions)]
    return df


st.title("LendLake portfolio dashboard")
st.caption(f"Home and personal loan book as of {pd.Timestamp(month):%d %b %Y}")

book = filtered(summary)
now = book[book["snapshot_month"] == month].sum(numeric_only=True)
prev_month = pd.Timestamp(month) - pd.offsets.MonthEnd(1)
prev = book[pd.to_datetime(book["snapshot_month"]) == prev_month].sum(numeric_only=True)

tiles = st.columns(6)
tiles[0].metric("Principal outstanding", crore(now["outstanding_principal"]),
                f"{(now['outstanding_principal'] / prev['outstanding_principal'] - 1):.1%} MoM"
                if prev["outstanding_principal"] else None)
tiles[1].metric("Active loans", f"{int(now['active_loans']):,}")
tiles[2].metric("Disbursed this month", crore(now["amount_disbursed"]))
tiles[3].metric("PAR 30+", pct(now["par30_principal"], now["outstanding_principal"]))
tiles[4].metric("GNPA (90+)", pct(now["npa_principal"], now["outstanding_principal"]))
tiles[5].metric("Collection efficiency", pct(now["collected_against_demand"], now["demand_due"]))

left, right = st.columns(2)

with left:
    st.subheader("Monthly disbursements")
    trend = book.groupby(["snapshot_month", "product_code"], as_index=False)["amount_disbursed"].sum()
    trend["amount_cr"] = trend["amount_disbursed"] / 1e7
    st.altair_chart(
        alt.Chart(trend).mark_bar().encode(
            x=alt.X("yearmonth(snapshot_month):T", title=None),
            y=alt.Y("amount_cr:Q", title="₹ Cr"),
            color=alt.Color("product_code:N", title="Product"),
            tooltip=["product_code", alt.Tooltip("amount_cr:Q", format=",.2f")],
        ).properties(height=300),
        use_container_width=True,
    )

with right:
    st.subheader("DPD distribution (principal outstanding)")
    dpd = query(f"""
        select d.dpd_bucket, d.bucket_order, d.product_code, b.region,
               sum(d.outstanding_principal) as pos, sum(d.loan_count) as loans
        from gold.mart_delinquency_buckets d join gold.dim_branch b using (branch_code)
        where d.snapshot_month = date '{pd.Timestamp(month):%Y-%m-%d}'
        group by all
    """)
    dpd = filtered(dpd).groupby(["dpd_bucket", "bucket_order"], as_index=False)[["pos", "loans"]].sum()
    dpd["pos_cr"] = dpd["pos"] / 1e7
    order = dpd.sort_values("bucket_order")["dpd_bucket"].tolist()
    st.altair_chart(
        alt.Chart(dpd).mark_bar().encode(
            x=alt.X("dpd_bucket:N", sort=order, title="Days past due"),
            y=alt.Y("pos_cr:Q", title="₹ Cr", scale=alt.Scale(type="symlog")),
            color=alt.Color("dpd_bucket:N", sort=order, legend=None,
                            scale=alt.Scale(domain=order, range=BUCKET_COLORS)),
            tooltip=["dpd_bucket", "loans", alt.Tooltip("pos_cr:Q", format=",.2f")],
        ).properties(height=300),
        use_container_width=True,
    )

left, right = st.columns(2)

with left:
    st.subheader("Vintage curves: ever 30+ DPD")
    vintage = query("select * from gold.mart_vintage_analysis")
    if products:
        vintage = vintage[vintage["product_code"].isin(products)]
    vintage["cohort_quarter"] = pd.PeriodIndex(pd.to_datetime(vintage["cohort_month"]), freq="Q").astype(str)
    curves = vintage.groupby(["cohort_quarter", "months_on_book"], as_index=False)[
        ["loans_ever_30_plus", "cohort_loans"]].sum()
    # only cohorts that have reached a given month on book count in its denominator
    curves["rate"] = curves["loans_ever_30_plus"] / curves["cohort_loans"]
    st.altair_chart(
        alt.Chart(curves).mark_line(point=True).encode(
            x=alt.X("months_on_book:Q", title="Months on book"),
            y=alt.Y("rate:Q", title="Loans ever 30+ DPD", axis=alt.Axis(format="%")),
            color=alt.Color("cohort_quarter:N", title="Cohort"),
            tooltip=["cohort_quarter", "months_on_book", alt.Tooltip("rate:Q", format=".2%")],
        ).properties(height=300),
        use_container_width=True,
    )

with right:
    st.subheader("Branch leaderboard")
    branches = query(f"""
        select * from gold.mart_branch_performance
        where snapshot_month = date '{pd.Timestamp(month):%Y-%m-%d}'
    """)
    branches = filtered(branches).sort_values("collection_rank")
    board = pd.DataFrame({
        "Rank": branches["collection_rank"],
        "Branch": branches["branch_name"],
        "Region": branches["region"],
        "POS (₹ Cr)": branches["outstanding_principal"] / 1e7,
        "Disbursed (₹ Cr)": branches["amount_disbursed"] / 1e7,
        "Collection eff.": branches["overall_collection_efficiency"],
        "PAR 30+": branches["par30_ratio"],
    })
    st.dataframe(
        board.style.format({
            "POS (₹ Cr)": "{:,.2f}", "Disbursed (₹ Cr)": "{:,.2f}",
            "Collection eff.": "{:.1%}", "PAR 30+": "{:.2%}",
        }),
        hide_index=True, use_container_width=True, height=320,
    )

st.caption("Product filter applies to all panels; region filter does not apply to vintage curves.")
