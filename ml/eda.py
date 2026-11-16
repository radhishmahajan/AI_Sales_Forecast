"""
STAGE 2 — Exploratory Data Analysis (EDA).

All analysis functions here are PURE: they take the cleaned sales DataFrame and return
tables. The same functions feed (a) the EDA notebook/report and (b) the FastAPI dashboard,
so a number on the dashboard always equals the number in the report.

Why EDA uses classified rows: raw lines include cancellations, returns, postage and
duplicates. Charting them as "sales" would be misleading, so sales analysis uses SALE rows
from ml.preprocessing (labels explained in Stage 3). The composition chart shows everything
that was set aside.

Run: python -m ml.eda   (needs Stage 3 output)
"""

from __future__ import annotations

import logging
from typing import Any

import matplotlib

matplotlib.use("Agg")  # render to files without a display (servers, CI)
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402

from ml import config  # noqa: E402
from ml.utils import atomic_write_json, atomic_write_text, to_json_safe, utc_now_iso  # noqa: E402

logger = logging.getLogger(__name__)
logging.getLogger("matplotlib.category").setLevel(logging.WARNING)

DOW_ORDER = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


# ===========================================================================
# Pure analysis functions (used by the API too)
# ===========================================================================
def trading_days(sales: pd.DataFrame) -> pd.DatetimeIndex:
    """Days on which the shop recorded at least one sale."""
    return pd.DatetimeIndex(sorted(sales["Date"].unique()))


def sales_kpis(sales: pd.DataFrame) -> dict[str, Any]:
    revenue = float(sales["Revenue"].sum())
    invoices = int(sales["InvoiceNo"].nunique())
    days = trading_days(sales)
    return {
        "total_revenue": round(revenue, 2),
        "total_quantity": int(sales["Quantity"].sum()),
        "total_transactions": invoices,
        "total_invoice_lines": int(len(sales)),
        "total_products": int(sales["StockCode"].nunique()),
        "total_customers": int(sales["CustomerID"].nunique()),
        "total_countries": int(sales["Country"].nunique()),
        "average_order_value": round(revenue / invoices, 2) if invoices else 0.0,
        "average_lines_per_order": round(len(sales) / invoices, 2) if invoices else 0.0,
        "trading_days": int(len(days)),
        "average_daily_revenue": round(revenue / len(days), 2) if len(days) else 0.0,
        "first_date": sales["InvoiceDate"].min(),
        "last_date": sales["InvoiceDate"].max(),
    }


def sales_over_time(sales: pd.DataFrame, freq: str = "D") -> pd.DataFrame:
    """Revenue, quantity, invoices and customers per period. freq: D, W, M or Y."""
    rule = {"D": "D", "W": "W-SUN", "M": "MS", "Y": "YS"}[freq]
    g = sales.set_index("InvoiceDate").resample(rule)
    out = pd.DataFrame(
        {
            "revenue": g["Revenue"].sum().round(2),
            "quantity": g["Quantity"].sum(),
            "transactions": g["InvoiceNo"].nunique(),
            "customers": g["CustomerID"].nunique(),
        }
    )
    if freq == "D":
        out = out[out["transactions"] > 0]  # days the shop was closed are not "zero sales days"
    out.index.name = "period"
    out = out.reset_index()
    first, last = sales["InvoiceDate"].min(), sales["InvoiceDate"].max()
    if freq == "M":
        out["is_partial"] = (out["period"].dt.to_period("M") == first.to_period("M")) & (first.day > 1) | (
            (out["period"].dt.to_period("M") == last.to_period("M")) & (last.day < last.days_in_month)
        )
    elif freq == "W":
        out["is_partial"] = (out["period"] == out["period"].min()) | (out["period"] == out["period"].max())
    else:
        out["is_partial"] = False
    return out


def product_performance(sales: pd.DataFrame) -> pd.DataFrame:
    g = sales.groupby("StockCode", observed=True)
    perf = pd.DataFrame(
        {
            "Description": g["Description"].first(),
            "quantity": g["Quantity"].sum(),
            "revenue": g["Revenue"].sum().round(2),
            "transactions": g["InvoiceNo"].nunique(),
            "sale_days": g["Date"].nunique(),
            "customers": g["CustomerID"].nunique(),
            "first_sale": g["Date"].min(),
            "last_sale": g["Date"].max(),
        }
    ).reset_index()
    total = perf["revenue"].sum()
    perf["revenue_share_pct"] = (100 * perf["revenue"] / total).round(4) if total else 0.0
    return perf.sort_values("revenue", ascending=False).reset_index(drop=True)


def top_products(sales: pd.DataFrame, by: str = "quantity", n: int = 10) -> pd.DataFrame:
    return product_performance(sales).nlargest(n, by).reset_index(drop=True)


def slow_moving_products(sales: pd.DataFrame, n: int = 10, min_sale_days: int = 1) -> pd.DataFrame:
    """Least-selling products by total quantity (ties broken by fewer sale days)."""
    perf = product_performance(sales)
    perf = perf[perf["sale_days"] >= min_sale_days]
    return perf.sort_values(["quantity", "sale_days", "revenue"]).head(n).reset_index(drop=True)


def demand_variability(sales: pd.DataFrame, min_sale_days: int = 1) -> pd.DataFrame:
    """Mean, std and coefficient of variation (CV) of DAILY demand for each product.

    Observation window per product = trading days from its first to its last sale.
    Trading days inside the window with no sale count as 0 demand; days before the first /
    after the last sale and days the shop was closed are NOT counted.
    CV = std / mean: < 0.5 smooth, 0.5-1 moderate, > 1 erratic/intermittent demand.
    """
    days = trading_days(sales)
    day_pos = pd.Series(np.arange(len(days)), index=days)
    daily = sales.groupby(["StockCode", "Date"], observed=True)["Quantity"].sum().reset_index()
    daily["pos"] = daily["Date"].map(day_pos)
    g = daily.groupby("StockCode", observed=True)
    stats = pd.DataFrame(
        {
            "sum": g["Quantity"].sum().astype("float64"),
            "sumsq": g["Quantity"].apply(lambda s: float((s.astype("float64") ** 2).sum())),
            "sale_days": g["Quantity"].size(),
            "first": g["pos"].min(),
            "last": g["pos"].max(),
        }
    )
    stats["window_days"] = stats["last"] - stats["first"] + 1
    n = stats["window_days"].astype("float64")
    mean = stats["sum"] / n
    var = ((stats["sumsq"] - n * mean**2) / (n - 1)).where(n > 1)
    out = pd.DataFrame(
        {
            "mean_daily_demand": mean.round(4),
            "std_daily_demand": np.sqrt(var.clip(lower=0)).round(4),
            "sale_days": stats["sale_days"],
            "window_days": stats["window_days"],
        }
    )
    out["cv"] = (out["std_daily_demand"] / out["mean_daily_demand"]).round(4)
    out["sale_day_ratio"] = (out["sale_days"] / out["window_days"]).round(4)
    out["variability_class"] = pd.cut(
        out["cv"], bins=[-np.inf, 0.5, 1.0, np.inf], labels=["Smooth", "Moderate", "Erratic"]
    ).astype("string")
    desc = sales.groupby("StockCode", observed=True)["Description"].first()
    out.insert(0, "Description", desc)
    out = out[out["sale_days"] >= min_sale_days]
    return out.reset_index().sort_values("cv", ascending=False).reset_index(drop=True)


def country_summary(sales: pd.DataFrame) -> pd.DataFrame:
    g = sales.groupby("Country", observed=True)
    out = pd.DataFrame(
        {
            "revenue": g["Revenue"].sum().round(2),
            "quantity": g["Quantity"].sum(),
            "transactions": g["InvoiceNo"].nunique(),
            "customers": g["CustomerID"].nunique(),
        }
    ).reset_index()
    out["revenue_share_pct"] = (100 * out["revenue"] / out["revenue"].sum()).round(3)
    out["average_order_value"] = (out["revenue"] / out["transactions"]).round(2)
    return out.sort_values("revenue", ascending=False).reset_index(drop=True)


def customer_summary(sales: pd.DataFrame, n: int = 10) -> dict[str, Any]:
    known = sales.dropna(subset=["CustomerID"])
    g = known.groupby("CustomerID", observed=True)
    per = pd.DataFrame(
        {"revenue": g["Revenue"].sum().round(2), "orders": g["InvoiceNo"].nunique(), "country": g["Country"].first()}
    ).reset_index()
    orders = per["orders"]
    return {
        "identified_customers": int(len(per)),
        "revenue_share_identified_pct": round(100 * known["Revenue"].sum() / sales["Revenue"].sum(), 2),
        "orders_per_customer": {
            "mean": round(float(orders.mean()), 2),
            "median": float(orders.median()),
            "max": int(orders.max()) if len(orders) else 0,
        },
        "one_time_customers_pct": round(100 * float((orders == 1).mean()), 2) if len(orders) else 0.0,
        "repeat_customers_pct": round(100 * float((orders > 1).mean()), 2) if len(orders) else 0.0,
        "top_customers": per.nlargest(n, "revenue").to_dict(orient="records"),
        "orders_distribution": orders.clip(upper=50).value_counts().sort_index().to_dict(),
    }


def day_of_week_pattern(sales: pd.DataFrame) -> pd.DataFrame:
    s = sales.assign(dow=sales["InvoiceDate"].dt.day_name())
    days = s.groupby("dow")["Date"].nunique()
    g = s.groupby("dow")
    out = pd.DataFrame(
        {"revenue": g["Revenue"].sum().round(2), "quantity": g["Quantity"].sum(), "transactions": g["InvoiceNo"].nunique()}
    ).reindex(DOW_ORDER).fillna(0)
    out["trading_days"] = days.reindex(DOW_ORDER).fillna(0).astype(int)
    out["avg_revenue_per_trading_day"] = (out["revenue"] / out["trading_days"].replace(0, np.nan)).round(2).fillna(0)
    out.index.name = "day_of_week"
    return out.reset_index()


def hourly_pattern(sales: pd.DataFrame) -> pd.DataFrame:
    g = sales.groupby(sales["InvoiceDate"].dt.hour)
    out = pd.DataFrame(
        {"transactions": g["InvoiceNo"].nunique(), "revenue": g["Revenue"].sum().round(2), "quantity": g["Quantity"].sum()}
    )
    out.index.name = "hour"
    return out.reset_index()


def transaction_composition(classified: pd.DataFrame) -> pd.DataFrame:
    g = classified.groupby("TransactionType", observed=True)
    return pd.DataFrame({"rows": g.size(), "quantity": g["Quantity"].sum(), "revenue": g["Revenue"].sum().round(2)}).reset_index()


# ===========================================================================
# Charts (Matplotlib/Seaborn) with business interpretations
# ===========================================================================
def _save(fig: plt.Figure, name: str) -> str:
    config.FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(config.FIGURES_DIR / name, dpi=130)
    plt.close(fig)
    return f"figures/{name}"


def _gbp(x: float, _pos: Any = None) -> str:
    if abs(x) >= 1e6:
        return f"£{x/1e6:.1f}M"
    if abs(x) >= 1e3:
        return f"£{x/1e3:.0f}k"
    return f"£{x:.0f}"


def generate_eda(sales: pd.DataFrame, classified: pd.DataFrame | None = None) -> dict[str, Any]:
    """Create every EDA chart + interpretation; return the EDA report dict."""
    sns.set_theme(style="whitegrid")
    charts: list[dict[str, str]] = []
    kpis = sales_kpis(sales)

    def add(title: str, path: str, interpretation: str) -> None:
        charts.append({"title": title, "file": path, "interpretation": interpretation})

    # 0) composition
    if classified is not None:
        comp = transaction_composition(classified).sort_values("rows")
        fig, ax = plt.subplots(figsize=(9, 4.5))
        ax.barh(comp["TransactionType"].astype(str), comp["rows"], color="#4C72B0")
        ax.set_xscale("log")
        ax.set_title("Invoice lines by transaction type (after removing duplicates)")
        ax.set_xlabel("Number of invoice lines (log scale)")
        ax.set_ylabel("Transaction type")
        sale_share = 100 * comp.set_index("TransactionType").loc["SALE", "rows"] / comp["rows"].sum()
        add("Transaction composition", _save(fig, "02_transaction_composition.png"),
            f"{sale_share:.1f}% of lines are genuine product sales. Returns, reversed orders, postage/fees and "
            "adjustments are kept out of demand so they do not distort forecasts.")

    # 1) daily
    daily = sales_over_time(sales, "D")
    fig, ax = plt.subplots(figsize=(11, 4.5))
    ax.plot(daily["period"], daily["revenue"], lw=0.8, alpha=0.5, label="Daily revenue")
    ax.plot(daily["period"], daily["revenue"].rolling(7, min_periods=1).mean(), lw=2, label="7-trading-day average")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_gbp))
    ax.set_title("Daily sales revenue (trading days only)")
    ax.set_xlabel("Date")
    ax.set_ylabel("Revenue (GBP)")
    ax.legend()
    peak = daily.loc[daily["revenue"].idxmax()]
    mavg = daily.groupby(daily["period"].dt.to_period("M").dt.to_timestamp())["revenue"].mean()
    hi_m, lo_m = mavg.idxmax(), mavg.idxmin()
    add("Daily sales", _save(fig, "02_daily_sales.png"),
        f"Revenue is noisy day to day (busiest day {peak['period']:%d %b %Y}: {_gbp(peak['revenue'])}; "
        f"daily std = {_gbp(daily['revenue'].std())}). Average revenue per trading day is highest in {hi_m:%B %Y} "
        f"({_gbp(mavg.max())}), {mavg.max() / mavg.min():.1f}x the lowest month ({lo_m:%B %Y}).")

    # 2) weekly
    weekly = sales_over_time(sales, "W")
    fig, ax1 = plt.subplots(figsize=(11, 4.5))
    ax1.bar(weekly["period"], weekly["quantity"], width=5, color="#8FB3DE", label="Units sold")
    ax1.set_ylabel("Units sold per week")
    ax2 = ax1.twinx()
    ax2.plot(weekly["period"], weekly["revenue"], color="#C44E52", lw=2, label="Revenue")
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_gbp))
    ax2.set_ylabel("Revenue per week (GBP)")
    ax2.grid(False)
    ax1.set_title("Weekly units sold and revenue (first and last weeks are partial)")
    ax1.set_xlabel("Week ending")
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left")
    full = weekly[~weekly["is_partial"] & (weekly["transactions"] > 0)]
    closed_weeks = int(((weekly["transactions"] == 0) & ~weekly["is_partial"]).sum())
    add("Weekly sales", _save(fig, "02_weekly_sales.png"),
        f"Units and revenue move together. Full weeks range from {_gbp(full['revenue'].min())} to "
        f"{_gbp(full['revenue'].max())} revenue, so weekly planning must allow for a large swing."
        + (f" {closed_weeks} week(s) had no trading at all (holiday closure)." if closed_weeks else ""))

    # 3) monthly
    monthly = sales_over_time(sales, "M")
    fig, ax = plt.subplots(figsize=(11, 4.5))
    colors = ["#BBBBBB" if p else "#4C72B0" for p in monthly["is_partial"]]
    ax.bar(monthly["period"].dt.strftime("%b %Y"), monthly["revenue"], color=colors)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_gbp))
    ax.set_title("Monthly revenue (grey = partial month)")
    ax.set_xlabel("Month")
    ax.set_ylabel("Revenue (GBP)")
    plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
    fm = monthly[~monthly["is_partial"]]
    best = fm.loc[fm["revenue"].idxmax()]
    worst = fm.loc[fm["revenue"].idxmin()]
    add("Monthly revenue", _save(fig, "02_monthly_revenue.png"),
        f"Best full month: {best['period']:%B %Y} ({_gbp(best['revenue'])}); weakest: {worst['period']:%B %Y} "
        f"({_gbp(worst['revenue'])}). With only ~one year of data this is a single seasonal cycle, so it is "
        "described as an observed peak in this period, not a proven yearly pattern.")

    # 4/5) top products
    for by, fname, title in (("quantity", "02_top_products_quantity.png", "Top 10 products by units sold"),
                             ("revenue", "02_top_products_revenue.png", "Top 10 products by revenue")):
        top = top_products(sales, by, 10).iloc[::-1]
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.barh(top["Description"].str.slice(0, 38), top[by], color="#55A868" if by == "quantity" else "#4C72B0")
        if by == "revenue":
            ax.xaxis.set_major_formatter(mticker.FuncFormatter(_gbp))
        ax.set_title(title)
        ax.set_xlabel("Units sold" if by == "quantity" else "Revenue (GBP)")
        ax.set_ylabel("Product")
        leader = top.iloc[-1]
        avg_price = top["revenue"].sum() / top["quantity"].sum()
        share = 100 * top[by].sum() / (sales["Quantity"].sum() if by == "quantity" else sales["Revenue"].sum())
        add(title, _save(fig, fname),
            f"'{leader['Description']}' leads with {leader[by]:,.0f}{' units' if by == 'quantity' else ' GBP'}. "
            f"These 10 products account for {share:.1f}% of all {'units' if by == 'quantity' else 'revenue'}; "
            f"their average selling price is £{avg_price:.2f} per unit.")

    # 6) demand variability
    var = demand_variability(sales, min_sale_days=20)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    sns.histplot(var["cv"].clip(upper=6), bins=40, ax=ax, color="#8172B3")
    ax.axvline(1.0, color="black", ls="--", lw=1, label="CV = 1 (erratic above)")
    ax.set_title("Daily demand variability per product (products with >= 20 sale days)")
    ax.set_xlabel("Coefficient of variation of daily demand (std / mean, clipped at 6)")
    ax.set_ylabel("Number of products")
    ax.legend()
    erratic = 100 * (var["cv"] > 1).mean()
    add("Product demand variability", _save(fig, "02_demand_variability.png"),
        f"{erratic:.0f}% of products with >= 20 sale days have CV > 1 (median CV {var['cv'].median():.2f}; "
        f"median share of trading days with a sale {100 * var['sale_day_ratio'].median():.0f}%). Daily product demand is "
        "intermittent and bursty, so safety stock matters and day-level forecast errors will be large.")

    # 7) countries
    countries = country_summary(sales).head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(countries["Country"], countries["revenue"], color="#4C72B0")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_gbp))
    ax.set_title("Revenue by country (top 12, log scale)")
    ax.set_xlabel("Revenue (GBP, log scale)")
    ax.set_ylabel("Country")
    cs = country_summary(sales)
    lead_c = cs.iloc[0]
    others = ", ".join(cs["Country"].iloc[1:5])
    add("Country-wise revenue", _save(fig, "02_country_revenue.png"),
        f"{lead_c['Country']} generates {lead_c['revenue_share_pct']:.1f}% of revenue; a log scale keeps the next "
        f"markets ({others}) visible. Demand is dominated by one market.")

    # 8) day of week
    dow = day_of_week_pattern(sales)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(dow["day_of_week"], dow["avg_revenue_per_trading_day"], color="#4C72B0")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_gbp))
    ax.set_title("Average revenue per trading day, by weekday")
    ax.set_xlabel("Day of week")
    ax.set_ylabel("Average revenue per trading day (GBP)")
    open_dow = dow[dow["trading_days"] > 0]
    closed = dow.loc[dow["trading_days"] == 0, "day_of_week"].tolist()
    add("Day-of-week pattern", _save(fig, "02_day_of_week.png"),
        f"Busiest weekday: {open_dow.loc[open_dow['avg_revenue_per_trading_day'].idxmax(), 'day_of_week']}; quietest: "
        f"{open_dow.loc[open_dow['avg_revenue_per_trading_day'].idxmin(), 'day_of_week']}. "
        f"No trading on: {', '.join(closed) or 'none'} — the forecast treats these as closed days.")

    # 9) hourly
    hourly = hourly_pattern(sales)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(hourly["hour"].astype(str), hourly["transactions"], color="#55A868")
    ax.set_title("Orders by hour of day")
    ax.set_xlabel("Hour of day (24h)")
    ax.set_ylabel("Number of orders (invoices)")
    ph = hourly.loc[hourly["transactions"].idxmax(), "hour"]
    biz = 100 * hourly.loc[hourly["hour"].between(8, 17), "transactions"].sum() / hourly["transactions"].sum()
    add("Hourly pattern", _save(fig, "02_hourly_orders.png"),
        f"Orders peak around {ph}:00; {biz:.1f}% of orders arrive between 08:00 and 17:59 "
        f"(first hour with orders: {hourly['hour'].min()}:00, last: {hourly['hour'].max()}:00).")

    # 10) customers
    cust = customer_summary(sales)
    dist = pd.Series(cust["orders_distribution"])
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar(dist.index.astype(int), dist.values, color="#DD8452")
    ax.set_yscale("log")
    ax.set_title("Orders per identified customer (50 = 50 or more)")
    ax.set_xlabel("Number of orders in the period")
    ax.set_ylabel("Customers (log scale)")
    add("Customer purchase frequency", _save(fig, "02_customer_frequency.png"),
        f"{cust['repeat_customers_pct']:.0f}% of identified customers ordered more than once (median "
        f"{cust['orders_per_customer']['median']:.0f} orders, maximum {cust['orders_per_customer']['max']}). "
        f"Identified customers generate {cust['revenue_share_identified_pct']:.1f}% of revenue.")

    report = {
        "report": "Stage 2 - Exploratory Data Analysis",
        "generated_at": utc_now_iso(),
        "data_used": "SALE rows from Stage 3 classification (duplicates, cancellations, returns, postage/fees and adjustments excluded).",
        "kpis": kpis,
        "charts": charts,
        "monthly": monthly,
        "top_products_quantity": top_products(sales, "quantity", 10),
        "top_products_revenue": top_products(sales, "revenue", 10),
        "least_selling_products": slow_moving_products(sales, 10),
        "countries": country_summary(sales).head(15),
        "customers": cust,
        "day_of_week": dow,
        "hourly": hourly,
        "variability_summary": {
            "products_analysed": int(len(var)),
            "smooth_pct": round(100 * float((var["variability_class"] == "Smooth").mean()), 2),
            "moderate_pct": round(100 * float((var["variability_class"] == "Moderate").mean()), 2),
            "erratic_pct": round(100 * float((var["variability_class"] == "Erratic").mean()), 2),
            "median_cv": round(float(var["cv"].median()), 3),
        },
        "seasonality_note": "The data covers ~12 months (Dec 2010 - Dec 2011): one seasonal cycle. Annual seasonality cannot be statistically confirmed.",
    }
    return to_json_safe(report)


def render_markdown(report: dict[str, Any]) -> str:
    k = report["kpis"]
    lines = [
        "# Stage 2 — Exploratory Data Analysis\n",
        f"_Generated {report['generated_at']}. Data: {report['data_used']}_\n",
        "## Key figures\n",
        f"- Gross fulfilled revenue: **£{k['total_revenue']:,.2f}**",
        f"- Units sold: **{k['total_quantity']:,}**",
        f"- Orders (invoices): **{k['total_transactions']:,}**; average order value **£{k['average_order_value']:,.2f}**",
        f"- Products: **{k['total_products']:,}**; identified customers: **{k['total_customers']:,}**; countries: **{k['total_countries']}**",
        f"- Trading days: **{k['trading_days']}**; average daily revenue **£{k['average_daily_revenue']:,.2f}**\n",
        f"> {report['seasonality_note']}\n",
    ]
    for c in report["charts"]:
        lines += [f"## {c['title']}\n", f"![{c['title']}]({c['file']})\n", f"**Interpretation:** {c['interpretation']}\n"]
    return "\n".join(lines)


def run(sales: pd.DataFrame | None = None, classified: pd.DataFrame | None = None) -> dict[str, Any]:
    from ml.preprocessing import load_classified, load_clean_sales

    sales = load_clean_sales() if sales is None else sales
    if classified is None:
        try:
            classified = load_classified()
        except FileNotFoundError:
            classified = None
    report = generate_eda(sales, classified)
    atomic_write_json(config.REPORTS_DIR / "02_eda_report.json", report)
    atomic_write_text(config.REPORTS_DIR / "02_eda_report.md", render_markdown(report))
    return report


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rep = run()
    print(f"EDA done: {len(rep['charts'])} charts saved in data/reports/figures/")
    for c in rep["charts"]:
        print(" -", c["title"], "->", c["interpretation"][:110])
