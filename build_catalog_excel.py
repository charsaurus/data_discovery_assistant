"""
One-off generator script: builds data/catalog/*.xlsx — one workbook per
data source, each with two sheets:

    "Summary"      - source metadata (owner, contact, access level, etc.)
                     as a two-column key/value table
    "Sample Data"  - header row of field names + realistic synthetic rows,
                     so the workbook actually mimics what the real source
                     looks like, not just a text description of it.

Run once with: python3 build_catalog_excel.py
Regenerate any time by re-running it (overwrites existing files).
"""

import random
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

random.seed(42)

OUT_DIR = Path(__file__).resolve().parent / "data" / "catalog"
OUT_DIR.mkdir(parents=True, exist_ok=True)

N_SAMPLE_ROWS = 12

# --- Shared reference values, reused across generators for consistency ------
MODELS = ["Aria Sedan", "Voyager SUV", "Bolt Compact", "Ranger Pickup", "Volt EV"]
TRIMS = ["Base", "Sport", "Limited", "Premium"]
REGIONS = ["Northeast", "Midwest", "South", "West"]
BRANCHES = [f"BR-{i:02d}" for i in range(1, 6)]
SALESPEOPLE = [f"SP-{100+i}" for i in range(1, 16)]


def rand_date(start_year=2024, end_year=2026):
    start = date(start_year, 1, 1)
    end = date(end_year, 7, 27)
    delta = (end - start).days
    return (start + timedelta(days=random.randint(0, delta))).isoformat()


def rand_month(start_year=2024, end_year=2026):
    y = random.randint(start_year, end_year)
    m = random.randint(1, 12)
    return f"{y}-{m:02d}"


def cust_id(i=None):
    return f"CUST-{random.randint(1000, 9999)}" if i is None else f"CUST-{1000+i}"


def vin():
    return "VIN" + "".join(random.choices("ABCDEFGHJKLMNPRSTUVWXYZ0123456789", k=14))


# --- Per-source definitions: metadata + field generator ---------------------

def gen_001():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        rows.append({
            "customer_id": cust_id(),
            "purchase_date": rand_date(),
            "vehicle_model": random.choice(MODELS),
            "trim_level": random.choice(TRIMS),
            "price_paid": random.randint(22000, 58000),
            "financing_type": random.choice(["cash", "loan", "lease"]),
            "trade_in_value": random.choice([0, 0, random.randint(3000, 15000)]),
            "dealer_branch_id": random.choice(BRANCHES),
            "salesperson_id": random.choice(SALESPEOPLE),
        })
    return rows


def gen_002():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        rows.append({
            "model": random.choice(MODELS),
            "trim_level": random.choice(TRIMS),
            "region": random.choice(REGIONS),
            "avg_market_price": random.randint(21000, 60000),
            "price_month": rand_month(),
            "new_or_used": random.choice(["new", "used"]),
        })
    return rows


def gen_003():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        rows.append({
            "session_id": f"SESS-{random.randint(100000, 999999)}",
            "customer_id": random.choice([cust_id(), "", ""]),
            "model_viewed": random.choice(MODELS),
            "page_type": random.choice(["model_overview", "pricing", "gallery", "compare", "contact_dealer"]),
            "time_on_page_seconds": random.randint(8, 420),
            "device_type": random.choice(["mobile", "desktop", "tablet"]),
            "visit_date": rand_date(),
        })
    return rows


def gen_004():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        converted = random.random() < 0.35
        rows.append({
            "booking_id": f"BK-{random.randint(10000, 99999)}",
            "customer_id": cust_id(),
            "model": random.choice(MODELS),
            "branch_id": random.choice(BRANCHES),
            "booking_date": rand_date(),
            "converted_to_sale": converted,
            "days_to_conversion": random.randint(1, 30) if converted else "",
        })
    return rows


def gen_005():
    rows = []
    for model in MODELS:
        for trim in TRIMS:
            rows.append({
                "model": model,
                "trim_level": trim,
                "model_year": random.choice([2025, 2026]),
                "engine_type": random.choice(["2.0L I4", "3.5L V6", "Electric Motor", "2.5L Hybrid"]),
                "fuel_economy_mpg": random.choice(["N/A (EV)", str(random.randint(22, 42))]),
                "body_category": {
                    "Aria Sedan": "sedan", "Voyager SUV": "SUV", "Bolt Compact": "hatchback",
                    "Ranger Pickup": "truck", "Volt EV": "EV",
                }[model],
                "price_msrp": random.randint(23000, 62000),
            })
    return rows[:N_SAMPLE_ROWS]


def gen_006():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        rows.append({
            "model": random.choice(MODELS),
            "region": random.choice(REGIONS),
            "week_starting": rand_date(),
            "search_volume_index": random.randint(10, 100),
        })
    return rows


def gen_007():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        rows.append({
            "sale_id": f"SALE-{random.randint(100000, 999999)}",
            "dealer_branch_id": random.choice(BRANCHES),
            "model": random.choice(MODELS),
            "trim_level": random.choice(TRIMS),
            "sale_price": random.randint(22000, 60000),
            "sale_date": rand_date(),
            "salesperson_id": random.choice(SALESPEOPLE),
            "customer_id": cust_id(),
        })
    return rows


def gen_008():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        rows.append({
            "customer_id": cust_id(),
            "age_bracket": random.choice(["18-24", "25-34", "35-44", "45-54", "55-64", "65+"]),
            "income_bracket": random.choice(["<40k", "40k-70k", "70k-100k", "100k-150k", "150k+"]),
            "household_size": random.randint(1, 5),
            "occupation_category": random.choice(["Professional", "Manager", "Retired", "Self-employed", "Student", "Other"]),
            "survey_date": rand_date(),
        })
    return rows


def gen_009():
    competitors = ["AutoRival Corp", "DriveNow Motors", "Metro Auto Group"]
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        rows.append({
            "competitor_name": random.choice(competitors),
            "model_equivalent": random.choice(MODELS) + " (comparable)",
            "listed_price": random.randint(20000, 61000),
            "region": random.choice(REGIONS),
            "scrape_date": rand_date(),
        })
    return rows


def gen_010():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        accepted = random.random() < 0.6
        rows.append({
            "trade_in_id": f"TI-{random.randint(10000, 99999)}",
            "customer_id": cust_id(),
            "original_model": random.choice(MODELS),
            "model_year": random.choice([2019, 2020, 2021, 2022, 2023]),
            "condition_score": random.randint(3, 10),
            "appraised_value": random.randint(4000, 22000),
            "offer_accepted": accepted,
            "appraisal_date": rand_date(),
        })
    return rows


def gen_011():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        approved = random.random() < 0.75
        rows.append({
            "application_id": f"APP-{random.randint(100000, 999999)}",
            "customer_id": cust_id(),
            "loan_amount": random.randint(10000, 55000),
            "approved": approved,
            "interest_rate": round(random.uniform(3.5, 12.0), 2) if approved else "",
            "credit_score_band": random.choice(["300-579", "580-669", "670-739", "740-799", "800-850"]),
            "application_date": rand_date(),
        })
    return rows


def gen_012():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        responded = random.random() < 0.22
        rows.append({
            "campaign_id": f"CMP-{random.randint(1000, 9999)}",
            "channel": random.choice(["email", "sms", "paid_social", "display"]),
            "customer_id": cust_id(),
            "responded": responded,
            "conversion_value": random.randint(500, 5000) if responded and random.random() < 0.3 else "",
            "campaign_date": rand_date(),
        })
    return rows


def gen_013():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        rows.append({
            "model": random.choice(MODELS),
            "platform": random.choice(["twitter", "facebook", "instagram", "forums"]),
            "sentiment_score": round(random.uniform(-1, 1), 2),
            "mention_volume": random.randint(5, 800),
            "mention_date": rand_date(),
        })
    return rows


def gen_014():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        rows.append({
            "vin": vin(),
            "avg_mileage_per_month": random.randint(300, 2200),
            "driving_score": random.randint(40, 99),
            "region": random.choice(REGIONS),
            "reporting_month": rand_month(),
        })
    return rows


def gen_015():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        rows.append({
            "vin": vin(),
            "customer_id": cust_id(),
            "service_date": rand_date(),
            "service_type": random.choice(["Oil Change", "Tire Rotation", "Brake Service", "Battery Replacement", "General Inspection"]),
            "cost": random.randint(40, 950),
            "satisfaction_score": random.randint(1, 5),
        })
    return rows


def gen_016():
    rows = []
    for branch in BRANCHES:
        for model in MODELS:
            rows.append({
                "branch_id": branch,
                "model": model,
                "trim_level": random.choice(TRIMS),
                "stock_count": random.randint(0, 20),
                "days_on_lot": random.randint(1, 120),
                "snapshot_date": rand_date(2026, 2026),
            })
    return rows[:N_SAMPLE_ROWS]


def gen_017():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        rows.append({
            "model": random.choice(MODELS),
            "claim_type": random.choice(["Collision", "Theft", "Weather Damage", "Liability"]),
            "claim_amount": random.randint(500, 25000),
            "claim_date": rand_date(),
            "region": random.choice(REGIONS),
        })
    return rows


def gen_018():
    rows = []
    for _ in range(N_SAMPLE_ROWS):
        tier = random.choice(["Bronze", "Silver", "Gold", "Platinum"])
        referrals = random.randint(0, 8)
        rows.append({
            "customer_id": cust_id(),
            "loyalty_tier": tier,
            "referrals_made": referrals,
            "referrals_converted": random.randint(0, referrals),
            "redemptions_used": random.randint(0, 5),
            "enrollment_date": rand_date(2023, 2025),
        })
    return rows


SOURCES = [
    {
        "filename": "source_001_customer_purchase_history.xlsx",
        "meta": {
            "Source Name": "Customer Purchase History (CRM)",
            "Source ID": "SRC-001",
            "Owner / Department": "Sales Operations",
            "Approval Contact": "dataops-salesops@fictionalmotors.example",
            "Access Level": "Internal — Requires Manager Approval",
            "Update Frequency": "Daily",
            "Format": "SQL table (exportable to CSV/Excel)",
            "Keywords": "customer behaviour, purchase history, transactions, financing, trade-in, buying patterns",
            "Description": "Transactional record of every completed vehicle purchase across all dealer branches, going back to 2019. Captures what each customer bought, how they paid, and what they traded in. Primary source for understanding individual customer buying behaviour and financing preferences over time.",
        },
        "gen": gen_001,
    },
    {
        "filename": "source_002_market_price_index.xlsx",
        "meta": {
            "Source Name": "Regional Vehicle Market Price Index",
            "Source ID": "SRC-002",
            "Owner / Department": "Market Intelligence",
            "Approval Contact": "market-intel@fictionalmotors.example",
            "Access Level": "Internal — Open to all analysts",
            "Update Frequency": "Monthly",
            "Format": "CSV export from third-party pricing feed",
            "Keywords": "market price, pricing trends, regional pricing, average selling price, price benchmarking",
            "Description": "Monthly average market price by model, trim, and region, from an aggregated third-party pricing feed covering new and used vehicle listings. Used to benchmark internal pricing against the broader regional market and spot pricing trends over time.",
        },
        "gen": gen_002,
    },
    {
        "filename": "source_003_website_clickstream.xlsx",
        "meta": {
            "Source Name": "Website Clickstream & Browsing Behaviour",
            "Source ID": "SRC-003",
            "Owner / Department": "Digital Marketing",
            "Approval Contact": "digital-marketing-data@fictionalmotors.example",
            "Access Level": "Internal — Requires Privacy Review (contains session-level data)",
            "Update Frequency": "Daily",
            "Format": "JSON event stream, queryable via internal analytics warehouse",
            "Keywords": "customer behaviour, online behaviour, browsing, website activity, intent signals",
            "Description": "Clickstream data from the dealer group's website, capturing which models visitors browse, how long they spend on each page, and what device they use. Customer ID attached only when the visitor is logged in. Strong signal for early-stage purchase intent before a showroom visit.",
        },
        "gen": gen_003,
    },
    {
        "filename": "source_004_test_drive_bookings.xlsx",
        "meta": {
            "Source Name": "Test Drive Booking Logs",
            "Source ID": "SRC-004",
            "Owner / Department": "Showroom Operations",
            "Approval Contact": "showroom-ops@fictionalmotors.example",
            "Access Level": "Internal — Requires Manager Approval",
            "Update Frequency": "Daily",
            "Format": "SQL table",
            "Keywords": "customer behaviour, test drive, conversion, purchase intent, showroom activity",
            "Description": "Every test drive booked across all branches, including whether it later converted into a sale. One of the strongest behavioural signals for predicting purchase likelihood, reflecting real-world showroom engagement rather than passive browsing.",
        },
        "gen": gen_004,
    },
    {
        "filename": "source_005_vehicle_specifications.xlsx",
        "meta": {
            "Source Name": "Vehicle Specifications & Model Catalog",
            "Source ID": "SRC-005",
            "Owner / Department": "Product Data Team",
            "Approval Contact": "product-data@fictionalmotors.example",
            "Access Level": "Internal — Open to all analysts",
            "Update Frequency": "Quarterly (on new model releases)",
            "Format": "Excel workbook, one sheet per model year",
            "Keywords": "car specs, vehicle specifications, model information, engine, fuel economy, MSRP",
            "Description": "Master reference catalog of every vehicle model and trim sold by the group, including technical specifications and MSRP. Canonical source for static vehicle attributes — join against any transactional or behavioural dataset that only records a model name.",
        },
        "gen": gen_005,
    },
    {
        "filename": "source_006_popularity_search_trends.xlsx",
        "meta": {
            "Source Name": "Vehicle Popularity & Search Trends",
            "Source ID": "SRC-006",
            "Owner / Department": "Market Intelligence",
            "Approval Contact": "market-intel@fictionalmotors.example",
            "Access Level": "Internal — Open to all analysts",
            "Update Frequency": "Weekly",
            "Format": "CSV export from third-party search-trend feed",
            "Keywords": "popularity, demand trend, search interest, consumer interest, model popularity",
            "Description": "Weekly search-interest index per model and region, sourced from an aggregated third-party search-trend feed. Useful as a leading indicator of demand shifts before they show up in actual sales figures.",
        },
        "gen": gen_006,
    },
    {
        "filename": "source_007_dealer_sales_transactions.xlsx",
        "meta": {
            "Source Name": "Dealer Sales Transactions (Historical)",
            "Source ID": "SRC-007",
            "Owner / Department": "Finance",
            "Approval Contact": "finance-data@fictionalmotors.example",
            "Access Level": "Internal — Requires Finance Approval",
            "Update Frequency": "Daily",
            "Format": "SQL table",
            "Keywords": "sales transactions, revenue, historical sales, sale price, branch performance",
            "Description": "Complete historical record of every vehicle sale across all branches from 2019 onward, including final sale price, branch, and salesperson. Ground-truth revenue source, typically joined with customer or behavioural datasets to build outcome labels for predictive models.",
        },
        "gen": gen_007,
    },
    {
        "filename": "source_008_customer_demographics.xlsx",
        "meta": {
            "Source Name": "Customer Demographics Survey",
            "Source ID": "SRC-008",
            "Owner / Department": "Customer Insights",
            "Approval Contact": "customer-insights@fictionalmotors.example",
            "Access Level": "Internal — Requires Privacy Review",
            "Update Frequency": "Annual (voluntary survey, rolling collection)",
            "Format": "CSV export",
            "Keywords": "demographics, customer profile, income, household, occupation, customer segmentation",
            "Description": "Voluntary post-purchase survey capturing demographic attributes of customers who opt in. Response rate is roughly 30% of buyers, so coverage is partial — best used to build customer segments and enrich, rather than as a complete population dataset.",
        },
        "gen": gen_008,
    },
    {
        "filename": "source_009_competitor_pricing.xlsx",
        "meta": {
            "Source Name": "Competitor Pricing Feed",
            "Source ID": "SRC-009",
            "Owner / Department": "Competitive Intelligence (external vendor feed)",
            "Approval Contact": "competitive-intel@fictionalmotors.example",
            "Access Level": "Internal — Requires Manager Approval (licensed third-party data)",
            "Update Frequency": "Weekly",
            "Format": "CSV export from licensed vendor",
            "Keywords": "competitor prices, market comparison, competitive pricing, pricing strategy",
            "Description": "Listed prices for equivalent competitor models, scraped and licensed from a third-party vendor. Useful for competitive pricing strategy and comparing our pricing position against the local market.",
        },
        "gen": gen_009,
    },
    {
        "filename": "source_010_trade_in_valuation.xlsx",
        "meta": {
            "Source Name": "Trade-In Valuation Logs",
            "Source ID": "SRC-010",
            "Owner / Department": "Used Car Department",
            "Approval Contact": "used-car-dept@fictionalmotors.example",
            "Access Level": "Internal — Requires Manager Approval",
            "Update Frequency": "Daily",
            "Format": "SQL table",
            "Keywords": "trade-in, valuation, used car, appraisal, vehicle condition",
            "Description": "Every trade-in vehicle appraisal performed at any branch, whether or not the customer accepted the offer. Useful for understanding customer price sensitivity and feeding used-car inventory pipelines.",
        },
        "gen": gen_010,
    },
    {
        "filename": "source_011_finance_loan_approval.xlsx",
        "meta": {
            "Source Name": "Finance & Loan Approval Data",
            "Source ID": "SRC-011",
            "Owner / Department": "Finance / Credit Team",
            "Approval Contact": "credit-team@fictionalmotors.example",
            "Access Level": "Restricted — Requires Compliance Approval (contains credit data)",
            "Update Frequency": "Daily",
            "Format": "SQL table",
            "Keywords": "financing, loan approval, credit score, interest rate, affordability",
            "Description": "Records of every financing application submitted through the dealer group's in-house lending partner, including approval outcome and terms. Contains sensitive credit information; access requires compliance sign-off in addition to manager approval.",
        },
        "gen": gen_011,
    },
    {
        "filename": "source_012_marketing_campaign_response.xlsx",
        "meta": {
            "Source Name": "Marketing Campaign Response Data",
            "Source ID": "SRC-012",
            "Owner / Department": "Marketing",
            "Approval Contact": "marketing-data@fictionalmotors.example",
            "Access Level": "Internal — Open to all analysts",
            "Update Frequency": "Per campaign (roughly bi-weekly)",
            "Format": "CSV export from marketing automation platform",
            "Keywords": "campaign performance, marketing response, channel effectiveness, conversion",
            "Description": "Response and conversion data for every marketing campaign run across email, SMS, and paid social. Links campaign exposure to whether the customer went on to book a test drive or purchase — useful for attribution and outreach-response features.",
        },
        "gen": gen_012,
    },
    {
        "filename": "source_013_social_media_sentiment.xlsx",
        "meta": {
            "Source Name": "Social Media Sentiment Dataset",
            "Source ID": "SRC-013",
            "Owner / Department": "Brand & Communications",
            "Approval Contact": "brand-comms@fictionalmotors.example",
            "Access Level": "Internal — Open to all analysts",
            "Update Frequency": "Daily",
            "Format": "JSON export from licensed social listening tool",
            "Keywords": "sentiment, social media, brand perception, public opinion, model reputation",
            "Description": "Aggregated sentiment scores per model, drawn from public social media mentions via a licensed social listening tool. Useful for understanding brand perception trends over time, alongside harder sales/demand data.",
        },
        "gen": gen_013,
    },
    {
        "filename": "source_014_vehicle_telematics.xlsx",
        "meta": {
            "Source Name": "Vehicle Telematics & Usage Data (Post-Sale, Opt-In)",
            "Source ID": "SRC-014",
            "Owner / Department": "Connected Car Services",
            "Approval Contact": "connected-car@fictionalmotors.example",
            "Access Level": "Restricted — Requires Privacy & Compliance Approval",
            "Update Frequency": "Daily",
            "Format": "Time-series database export",
            "Keywords": "usage data, telematics, post-sale behaviour, driving patterns, mileage",
            "Description": "Post-sale vehicle usage data from customers who opted into the connected car program, capturing driving patterns and mileage. Only covers ~15% of the post-sale fleet (opt-in only). Useful for retention or upsell modeling.",
        },
        "gen": gen_014,
    },
    {
        "filename": "source_015_service_maintenance_records.xlsx",
        "meta": {
            "Source Name": "Service & Maintenance Records",
            "Source ID": "SRC-015",
            "Owner / Department": "After-Sales Service",
            "Approval Contact": "after-sales-service@fictionalmotors.example",
            "Access Level": "Internal — Requires Manager Approval",
            "Update Frequency": "Daily",
            "Format": "SQL table",
            "Keywords": "maintenance, customer satisfaction, retention, service history, after-sales",
            "Description": "Full service and maintenance history for every vehicle serviced at a group-owned service center, including customer satisfaction ratings. Frequently used for churn/retention modeling, since service satisfaction correlates with repeat purchases.",
        },
        "gen": gen_015,
    },
    {
        "filename": "source_016_inventory_stock_levels.xlsx",
        "meta": {
            "Source Name": "Inventory & Stock Levels by Branch",
            "Source ID": "SRC-016",
            "Owner / Department": "Inventory Management",
            "Approval Contact": "inventory-mgmt@fictionalmotors.example",
            "Access Level": "Internal — Open to all analysts",
            "Update Frequency": "Daily",
            "Format": "SQL table",
            "Keywords": "inventory, stock levels, supply, days on lot, availability",
            "Description": "Daily snapshot of vehicle stock levels at every branch, including how long each unit has been sitting on the lot. Useful for understanding supply-side constraints on sales strategy recommendations.",
        },
        "gen": gen_016,
    },
    {
        "filename": "source_017_insurance_claims_risk.xlsx",
        "meta": {
            "Source Name": "Insurance Claims & Risk Data (Partner Feed)",
            "Source ID": "SRC-017",
            "Owner / Department": "Insurance Partnerships",
            "Approval Contact": "insurance-partnerships@fictionalmotors.example",
            "Access Level": "Restricted — Requires Compliance Approval (third-party partner data)",
            "Update Frequency": "Monthly",
            "Format": "CSV export from insurance partner",
            "Keywords": "risk data, insurance, claims, vehicle risk profile, accident rate",
            "Description": "Aggregated insurance claims data from the group's insurance partner, broken out by model. Useful for understanding risk profiles by model, which can factor into pricing or promotional strategy.",
        },
        "gen": gen_017,
    },
    {
        "filename": "source_018_customer_loyalty_referral.xlsx",
        "meta": {
            "Source Name": "Customer Loyalty & Referral Program Data",
            "Source ID": "SRC-018",
            "Owner / Department": "CRM / Loyalty Team",
            "Approval Contact": "loyalty-team@fictionalmotors.example",
            "Access Level": "Internal — Open to all analysts",
            "Update Frequency": "Weekly",
            "Format": "SQL table",
            "Keywords": "loyalty, retention, referral, repeat customer, program engagement",
            "Description": "Tracks enrollment and activity in the dealer group's loyalty and referral program, including tier status and referrals made. Proxy for customer advocacy and long-term relationship strength — can factor into repeat-purchase or lifetime-value modeling.",
        },
        "gen": gen_018,
    },
]


def build_all():
    for src in SOURCES:
        path = OUT_DIR / src["filename"]
        summary_df = pd.DataFrame(
            [{"Field": k, "Value": v} for k, v in src["meta"].items()]
        )
        sample_rows = src["gen"]()
        sample_df = pd.DataFrame(sample_rows)

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            summary_df.to_excel(writer, sheet_name="Summary", index=False)
            sample_df.to_excel(writer, sheet_name="Sample Data", index=False)

        print(f"Built {path.name}  ({len(sample_df)} sample rows, {len(sample_df.columns)} fields)")

    print(f"\nDone: {len(SOURCES)} workbooks written to {OUT_DIR}")


if __name__ == "__main__":
    build_all()
