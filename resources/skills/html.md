# Skill: HTML Reports with displayHTML

> Recipes for building inline HTML reports in Databricks notebooks.
> Based on patterns from Beta Analysis dashboard, CD1 Product Mapping, and BDI dependency graph.

---

## Quick Table

```python
import sys
sys.path.insert(0, "/Workspace/Users/joshuawaller@synovus.com/_workspace_config/utils")
from export_utils import html_table

df = spark.sql("SELECT * FROM my_view LIMIT 100").toPandas()
displayHTML(html_table(df, title="My Report", subtitle="As of 2026-10-16",
                       number_cols=["balance", "count"]))
```

## Multi-Section Report

```python
from export_utils import html_report, html_table, collapsible_section

sections = [
    html_table(summary_df, title="Executive Summary", number_cols=["balance"]),
    collapsible_section("Detail by Product Group",
        html_table(detail_df, number_cols=["balance", "rate"])),
    collapsible_section("Appendix: Raw Data",
        html_table(raw_df)),
]

displayHTML(html_report(sections, report_title="Deposit Analysis", report_date="2026-10-16"))
```

## From-Scratch HTML (Full Control)

When you need custom layouts beyond tables:

```python
html = """
<meta charset="utf-8"/>
<style>
  :root {
    --bg: #f8f9fc; --card: #ffffff; --ink: #1a1a2e;
    --muted: #6b7280; --border: #e5e7eb; --accent: #2563eb;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0f172a; --card: #1e293b; --ink: #e2e8f0;
      --muted: #94a3b8; --border: #334155; --accent: #60a5fa;
    }
  }
  body { font-family: -apple-system, system-ui, sans-serif; color: var(--ink); margin: 0; }
  .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; margin: 12px 0; }
  .kpi-row { display: flex; gap: 16px; flex-wrap: wrap; }
  .kpi { flex: 1; min-width: 180px; text-align: center; }
  .kpi-value { font-size: 28px; font-weight: 700; color: var(--accent); }
  .kpi-label { font-size: 12px; color: var(--muted); text-transform: uppercase; }
</style>

<div class="container">
  <h1 style="font-size: 22px;">My Report</h1>

  <!-- KPI Cards -->
  <div class="card">
    <div class="kpi-row">
      <div class="kpi">
        <div class="kpi-value">$12.4B</div>
        <div class="kpi-label">Total Deposits</div>
      </div>
      <div class="kpi">
        <div class="kpi-value">3.82%</div>
        <div class="kpi-label">Wtd Avg Rate</div>
      </div>
      <div class="kpi">
        <div class="kpi-value">0.35</div>
        <div class="kpi-label">Avg Beta</div>
      </div>
    </div>
  </div>

  <!-- Collapsible sections -->
  <details open>
    <summary style="cursor:pointer; font-weight:600; padding:8px;">Detail by Product</summary>
    <!-- table here -->
  </details>
</div>
"""
displayHTML(html)
```

## Building HTML from DataFrames (Dynamic)

```python
# Build KPI values dynamically
total_bal = df["balance"].sum()
avg_rate = df["war"].mean()

# Build table rows dynamically
table_rows = ""
for _, row in df.iterrows():
    table_rows += f"""
    <tr>
        <td>{row['product']}</td>
        <td style="text-align:right">{row['balance']:,.0f}</td>
        <td style="text-align:right">{row['rate']:.3f}</td>
    </tr>"""

html = f"""
... (CSS from above) ...
<div class="kpi-value">${total_bal/1e9:.1f}B</div>
<table class="rpt-table">
  <thead><tr><th>Product</th><th>Balance</th><th>Rate</th></tr></thead>
  <tbody>{table_rows}</tbody>
</table>
"""
displayHTML(html)
```

## Interactive Features

### Collapsible Sections
```html
<details>
  <summary>Click to expand</summary>
  <div>Content here</div>
</details>
```

### Search/Filter with JavaScript
```html
<input id="search" type="text" placeholder="Filter..." oninput="
  const q = this.value.toLowerCase();
  document.querySelectorAll('tbody tr').forEach(r => {
    r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none';
  });
"/>
```

### Tabs
```html
<div class="tabs">
  <button onclick="showTab('tab1')">Summary</button>
  <button onclick="showTab('tab2')">Detail</button>
</div>
<div id="tab1">...</div>
<div id="tab2" style="display:none">...</div>
<script>
function showTab(id) {
  document.querySelectorAll('[id^=tab]').forEach(t => t.style.display = 'none');
  document.getElementById(id).style.display = 'block';
}
</script>
```

## Tips

* Always include `<meta charset="utf-8"/>` for special characters.
* Use CSS variables for dark/light mode support.
* `displayHTML()` renders inside an iframe — no access to notebook Python state.
* For charts inside HTML, use inline SVG or Canvas — no external JS libraries.
* Max height of displayHTML output is ~850px before scrolling.
