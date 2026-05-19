import streamlit as st
import pandas as pd
import plotly.express as px
from google.cloud import bigquery
from google.oauth2 import service_account


# ================= CONFIG =================

PROJECT_ID = "quick-commerce-ads"
TABLE_ID = "quick-commerce-ads.warehouse.blinkit_ads_intelligence"


# ================= PAGE CONFIG =================

st.set_page_config(
    page_title="Blinkit CPM Decision Dashboard",
    layout="wide",
    page_icon="📊"
)

# Hide Streamlit branding

st.markdown("""
<style>

/* Hide Streamlit menu */
#MainMenu {
    visibility: hidden;
}

/* Hide footer */
footer {
    visibility: hidden;
}

/* Hide header */
header {
    visibility: hidden;
}

/* Hide GitHub / Fork button */
.viewerBadge_container__1QSob,
.styles_viewerBadge__1yB5_,
.viewerBadge_link__1S137,
.stDeployButton {
    display: none !important;
}

</style>
""", unsafe_allow_html=True)

# ================= STYLE =================

st.markdown("""
<style>
[data-testid="stMetric"] {
    background-color: white;
    padding: 18px;
    border-radius: 16px;
    box-shadow: 0 4px 14px rgba(0,0,0,0.08);
    border-left: 6px solid #2f6fed;
}
.main-title {
    font-size: 36px;
    font-weight: 800;
    color: #1f2937;
}
.sub-title {
    font-size: 15px;
    color: #6b7280;
}
</style>
""", unsafe_allow_html=True)


# ================= LOAD DATA =================

@st.cache_data(ttl=300)
def load_data():
    credentials = service_account.Credentials.from_service_account_info(
        st.secrets["gcp_service_account"]
    )

    client = bigquery.Client(
        credentials=credentials,
        project=PROJECT_ID
    )

    query = f"""
    SELECT *
    FROM `{TABLE_ID}`
    ORDER BY timestamp DESC
    """

    df = client.query(query).to_dataframe(
        create_bqstorage_client=False
    )

    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    numeric_cols = [
        "product_placement_no",
        "ad_rank_no",
        "price",
        "cpm",
        "our_cpm",
        "competitor_cpm",
        "competitor_ad_rank_no",
        "competitor_placement_no",
        "cpm_difference",
        "recommended_cpm",
        "expected_saving"
    ]

    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    if "is_our_brand" in df.columns:
        df["is_our_brand_bool"] = (
            df["is_our_brand"]
            .astype(str)
            .str.upper()
            .eq("TRUE")
        )
    else:
        df["is_our_brand_bool"] = False

    df["brand_type"] = df["is_our_brand_bool"].apply(
        lambda x: "Slovic" if x else "Competitor"
    )

    df["time"] = df["timestamp"].dt.strftime("%H:%M")

    return df


df = load_data()


# ================= HEADER =================

st.markdown(
    '<div class="main-title">📊 Blinkit CPM Decision Dashboard</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="sub-title">Slovic vs Competitor CPM | Recommended CPM | Saving Opportunity | Action Report</div>',
    unsafe_allow_html=True
)

st.divider()

if df.empty:
    st.warning("No data found in BigQuery.")
    st.stop()


# ================= SIDEBAR =================

st.sidebar.header("🔍 Filters")

locations = ["All"] + sorted(df["location"].dropna().unique().tolist())
keywords = ["All"] + sorted(df["keyword"].dropna().unique().tolist())
actions = ["All"] + sorted(df["action_suggestion"].dropna().unique().tolist())

selected_location = st.sidebar.selectbox("Location", locations)
selected_keyword = st.sidebar.selectbox("Keyword", keywords)
selected_action = st.sidebar.selectbox("Action", actions)

date_range = st.sidebar.date_input(
    "Date Range",
    value=(df["date"].min(), df["date"].max())
)

filtered = df.copy()

if selected_location != "All":
    filtered = filtered[filtered["location"] == selected_location]

if selected_keyword != "All":
    filtered = filtered[filtered["keyword"] == selected_keyword]

if selected_action != "All":
    filtered = filtered[filtered["action_suggestion"] == selected_action]

if len(date_range) == 2:
    start_date, end_date = date_range
    filtered = filtered[
        (filtered["date"] >= start_date)
        & (filtered["date"] <= end_date)
    ]


# ================= KPI =================

c1, c2, c3, c4, c5, c6 = st.columns(6)

slovic_rows = filtered[filtered["brand_type"] == "Slovic"]
competitor_rows = filtered[filtered["brand_type"] == "Competitor"]

c1.metric("Keywords", filtered["keyword"].nunique())
c2.metric("Total Ads", len(filtered))
c3.metric("Slovic Ads", len(slovic_rows))
c4.metric("Competitor Ads", len(competitor_rows))

c5.metric(
    "Avg Slovic CPM",
    f"₹{slovic_rows['our_cpm'].mean():.0f}"
    if "our_cpm" in slovic_rows.columns and slovic_rows["our_cpm"].notna().any()
    else "₹0"
)

c6.metric(
    "Saving Opportunity",
    f"₹{filtered['expected_saving'].sum():.0f}"
    if "expected_saving" in filtered.columns and filtered["expected_saving"].notna().any()
    else "₹0"
)

st.divider()


# ================= BUSINESS INSIGHT =================

increase_count = filtered[filtered["action_suggestion"] == "INCREASE CPM"].shape[0]

decrease_count = filtered[
    filtered["action_suggestion"].isin(
        ["DECREASE CPM", "HIGH OVERPAY - REDUCE CPM"]
    )
].shape[0]

missing_count = filtered[filtered["action_suggestion"] == "SLOVIC MISSING"].shape[0]

st.subheader("💡 Business Insight")

st.info(
    f"""
🚀 **{increase_count}** cases need CPM increase.  
💰 **{decrease_count}** cases show overpaying / CPM reduction opportunity.  
⚠️ **{missing_count}** cases where Slovic is missing from ads.
"""
)


# ================= IMPORTANT GRAPHS =================

col1, col2 = st.columns(2)

with col1:
    st.subheader("🤖 Current CPM vs Recommended CPM")

    rec_df = filtered.dropna(subset=["our_cpm", "recommended_cpm"])

    if rec_df.empty:
        st.warning("No recommended CPM data available.")
    else:
        fig = px.bar(
            rec_df,
            x="keyword",
            y=["our_cpm", "recommended_cpm"],
            barmode="group",
            hover_data=[
                "location",
                "brand",
                "competitor_brand",
                "competitor_cpm",
                "cpm_difference",
                "expected_saving"
            ],
            title="Current CPM vs Recommended CPM"
        )
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)


with col2:
    st.subheader("⚡ Action Distribution")

    action_df = (
        filtered.groupby("action_suggestion", as_index=False)
        .size()
        .sort_values("size", ascending=False)
    )

    if action_df.empty:
        st.warning("No action data available.")
    else:
        fig = px.pie(
            action_df,
            names="action_suggestion",
            values="size",
            hole=0.45,
            title="Increase / Decrease / Missing / No Action"
        )
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)


col3, col4 = st.columns(2)

with col3:
    st.subheader("📈 CPM Difference by Keyword")

    diff_df = filtered.dropna(subset=["cpm_difference"])

    if diff_df.empty:
        st.warning("No CPM difference data available.")
    else:
        fig = px.bar(
            diff_df,
            x="keyword",
            y="cpm_difference",
            color="action_suggestion",
            hover_data=[
                "location",
                "brand",
                "our_cpm",
                "competitor_brand",
                "competitor_cpm",
                "recommended_cpm",
                "expected_saving"
            ],
            title="Competitor CPM - Slovic CPM"
        )
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)


with col4:
    st.subheader("🎯 Ad Rank vs CPM")

    rank_df = filtered.dropna(subset=["ad_rank_no", "our_cpm"])

    if rank_df.empty:
        st.warning("No rank data available.")
    else:
        fig = px.scatter(
            rank_df,
            x="ad_rank_no",
            y="our_cpm",
            size="price",
            color="action_suggestion",
            hover_data=[
                "keyword",
                "location",
                "brand",
                "product_name",
                "product_placement_no",
                "competitor_brand",
                "competitor_cpm"
            ],
            title="Ad Rank vs Slovic CPM"
        )
        fig.update_xaxes(autorange="reversed")
        fig.update_layout(height=420)
        st.plotly_chart(fig, use_container_width=True)


# ================= IMPORTANT ACTION TABLE =================

st.divider()
st.subheader("🚨 Important CPM Action Table")

show_all = st.checkbox("Show All Data", value=True)

if show_all:
    table_df = filtered.copy()
else:
    table_df = filtered[
        (
            (filtered["cpm_difference"].abs().fillna(0) >= 15)
            | (filtered["action_suggestion"] == "SLOVIC MISSING")
            | (filtered["action_suggestion"] == "HIGH OVERPAY - REDUCE CPM")
        )
    ].copy()

important_cols = [
    "timestamp",
    "location",
    "keyword",
    "brand",
    "product_name",
    "product_placement_no",
    "ad_rank_no",
    "price",
    "our_cpm",
    "competitor_brand",
    "competitor_product_name",
    "competitor_cpm",
    "cpm_difference",
    "recommended_cpm",
    "expected_saving",
    "action_suggestion",
]

important_cols = [col for col in important_cols if col in table_df.columns]

if "cpm_difference" in table_df.columns:
    table_df = table_df.sort_values(by="cpm_difference", ascending=True)

st.info(f"📊 Rows showing: {len(table_df)}")

format_cols = {
    "price": "₹{:.0f}",
    "our_cpm": "₹{:.0f}",
    "competitor_cpm": "₹{:.0f}",
    "recommended_cpm": "₹{:.0f}",
    "expected_saving": "₹{:.0f}",
    "cpm_difference": "{:.0f}",
    "product_placement_no": "{:.0f}",
    "ad_rank_no": "{:.0f}",
}

format_cols = {
    col: fmt for col, fmt in format_cols.items()
    if col in table_df.columns
}

st.dataframe(
    table_df[important_cols].style.format(format_cols),
    use_container_width=True,
    height=430
)

csv = table_df[important_cols].to_csv(index=False).encode("utf-8")

st.download_button(
    "⬇️ Download Important CPM Report",
    csv,
    "blinkit_important_cpm_report.csv",
    "text/csv"
)