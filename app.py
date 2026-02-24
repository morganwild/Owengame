#!/usr/bin/env python3
"""
House Buyer Tool — Web App
===========================
Run:  python app.py
Open: http://localhost:5000
"""

from flask import Flask, render_template_string, request, jsonify

# Import our existing calculators
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from house_buyer.mortgage import (
    calculate_mortgage, deposit_comparison, get_boe_base_rate, LENDER_SPREADS,
)
from house_buyer.stamp_duty import (
    calculate_stamp_duty, check_affordability, total_purchase_cost,
)
from house_buyer.land_registry import search_sold_prices, area_price_stats
from house_buyer.property_feeds import (
    search_property_feeds, area_property_stats, PropertySearchCriteria,
    _sources_configured as feeds_sources_configured,
)

app = Flask(__name__)

# Fetch base rate once on startup
BASE_RATE = get_boe_base_rate() or 4.50

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>House Buyer Tool</title>
<style>
  :root {
    --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
    --text: #f1f5f9; --muted: #94a3b8; --accent: #38bdf8;
    --green: #4ade80; --red: #f87171; --yellow: #fbbf24;
    --border: #475569; --radius: 12px;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    background: var(--bg); color: var(--text); line-height: 1.6;
    min-height: 100vh;
  }
  .container { max-width: 960px; margin: 0 auto; padding: 20px; }

  /* Header */
  header { text-align: center; padding: 40px 0 20px; }
  header h1 { font-size: 2rem; font-weight: 700; }
  header h1 span { color: var(--accent); }
  header p { color: var(--muted); margin-top: 4px; }
  .badge { display: inline-block; background: var(--surface2); color: var(--green);
    font-size: 0.75rem; padding: 3px 10px; border-radius: 20px; margin-top: 8px; }

  /* Tabs */
  .tabs { display: flex; gap: 4px; overflow-x: auto; padding: 10px 0 20px;
    border-bottom: 1px solid var(--border); margin-bottom: 24px; flex-wrap: wrap; }
  .tab { background: var(--surface); border: 1px solid var(--border); color: var(--muted);
    padding: 8px 16px; border-radius: 8px; cursor: pointer; font-size: 0.9rem;
    transition: all 0.2s; white-space: nowrap; }
  .tab:hover { border-color: var(--accent); color: var(--text); }
  .tab.active { background: var(--accent); color: var(--bg); border-color: var(--accent); font-weight: 600; }

  /* Panels */
  .panel { display: none; }
  .panel.active { display: block; }

  /* Cards */
  .card { background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius); padding: 24px; margin-bottom: 20px; }
  .card h2 { font-size: 1.25rem; margin-bottom: 16px; }
  .card h3 { font-size: 1rem; color: var(--accent); margin: 16px 0 8px; }

  /* Forms */
  .form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  @media (max-width: 600px) { .form-grid { grid-template-columns: 1fr; } }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .field label { font-size: 0.85rem; color: var(--muted); }
  .field input, .field select {
    background: var(--bg); border: 1px solid var(--border); color: var(--text);
    padding: 10px 12px; border-radius: 8px; font-size: 1rem; }
  .field input:focus, .field select:focus { outline: none; border-color: var(--accent); }

  /* Slider */
  .slider-row { display: flex; align-items: center; gap: 12px; }
  .slider-row input[type=range] { flex: 1; accent-color: var(--accent); }
  .slider-val { font-weight: 700; color: var(--accent); min-width: 50px; text-align: right; }

  /* Checkbox */
  .check-row { display: flex; align-items: center; gap: 8px; padding: 8px 0; }
  .check-row input { accent-color: var(--accent); width: 18px; height: 18px; }

  /* Buttons */
  .btn { background: var(--accent); color: var(--bg); border: none; padding: 12px 28px;
    border-radius: 8px; font-size: 1rem; font-weight: 600; cursor: pointer;
    transition: all 0.2s; margin-top: 16px; }
  .btn:hover { filter: brightness(1.1); transform: translateY(-1px); }
  .btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

  /* Results */
  .results { margin-top: 24px; }
  .result-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; }
  .stat { background: var(--bg); border-radius: 8px; padding: 16px; text-align: center; }
  .stat .label { font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }
  .stat .value { font-size: 1.5rem; font-weight: 700; margin-top: 4px; }
  .stat .value.green { color: var(--green); }
  .stat .value.red { color: var(--red); }
  .stat .value.accent { color: var(--accent); }
  .stat .sub { font-size: 0.8rem; color: var(--muted); margin-top: 2px; }

  /* Table */
  table { width: 100%; border-collapse: collapse; margin-top: 12px; }
  th { text-align: left; padding: 10px 12px; font-size: 0.8rem; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid var(--border); }
  td { padding: 10px 12px; border-bottom: 1px solid var(--surface2); font-size: 0.9rem; }
  tr:hover td { background: rgba(56,189,248,0.05); }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .highlight td { background: rgba(56,189,248,0.1); font-weight: 600; }

  /* Status badges */
  .pass { color: var(--green); font-weight: 700; }
  .fail { color: var(--red); font-weight: 700; }
  .warn { color: var(--yellow); }

  /* Loading */
  .loading { text-align: center; padding: 40px; color: var(--muted); }
  .spinner { display: inline-block; width: 20px; height: 20px; border: 2px solid var(--border);
    border-top-color: var(--accent); border-radius: 50%; animation: spin 0.6s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<div class="container">
  <header>
    <h1>House <span>Buyer</span> Tool</h1>
    <p>Mortgage, stamp duty, affordability, property data &amp; live house search</p>
    <div class="badge">BoE Base Rate: {{ base_rate }}%</div>
  </header>

  <div class="tabs">
    <div class="tab active" onclick="showTab('mortgage')">Mortgage Calculator</div>
    <div class="tab" onclick="showTab('deposit')">Deposit Comparison</div>
    <div class="tab" onclick="showTab('stamp')">Stamp Duty</div>
    <div class="tab" onclick="showTab('afford')">Affordability</div>
    <div class="tab" onclick="showTab('costs')">Purchase Costs</div>
    <div class="tab" onclick="showTab('area')">Area Prices</div>
    <div class="tab" onclick="showTab('feeds')">Property Feeds</div>
  </div>

  <!-- MORTGAGE CALCULATOR -->
  <div id="mortgage" class="panel active">
    <div class="card">
      <h2>Mortgage Repayment Calculator</h2>
      <div class="form-grid">
        <div class="field">
          <label>Property Price</label>
          <input type="number" id="m_price" value="300000" step="5000">
        </div>
        <div class="field">
          <label>Mortgage Term (years)</label>
          <input type="number" id="m_term" value="25" min="5" max="40">
        </div>
        <div class="field">
          <label>Rate Type</label>
          <select id="m_rate_type">
            <option value="best_fixed_2yr">Best Fixed 2yr</option>
            <option value="average_fixed_2yr" selected>Average Fixed 2yr</option>
            <option value="best_fixed_5yr">Best Fixed 5yr</option>
            <option value="average_fixed_5yr">Average Fixed 5yr</option>
            <option value="tracker">Tracker</option>
            <option value="standard_variable">Standard Variable</option>
          </select>
        </div>
      </div>
      <div style="margin-top:16px">
        <label style="font-size:0.85rem;color:var(--muted)">Deposit: <span id="m_dep_label">10%</span></label>
        <div class="slider-row">
          <span style="color:var(--muted);font-size:0.8rem">5%</span>
          <input type="range" id="m_deposit" min="5" max="50" value="10" step="1">
          <span style="color:var(--muted);font-size:0.8rem">50%</span>
          <span class="slider-val" id="m_dep_val">£30,000</span>
        </div>
      </div>
      <button class="btn" onclick="calcMortgage()">Calculate</button>
      <div id="m_results" class="results"></div>
    </div>
  </div>

  <!-- DEPOSIT COMPARISON -->
  <div id="deposit" class="panel">
    <div class="card">
      <h2>Deposit Comparison</h2>
      <p style="color:var(--muted);margin-bottom:16px">See how your deposit % changes monthly payments and total interest.</p>
      <div class="form-grid">
        <div class="field">
          <label>Property Price</label>
          <input type="number" id="d_price" value="300000" step="5000">
        </div>
        <div class="field">
          <label>Mortgage Term (years)</label>
          <input type="number" id="d_term" value="25">
        </div>
      </div>
      <button class="btn" onclick="calcDeposit()">Compare</button>
      <div id="d_results" class="results"></div>
    </div>
  </div>

  <!-- STAMP DUTY -->
  <div id="stamp" class="panel">
    <div class="card">
      <h2>Stamp Duty Calculator</h2>
      <div class="form-grid">
        <div class="field">
          <label>Property Price</label>
          <input type="number" id="s_price" value="300000" step="5000">
        </div>
      </div>
      <div class="check-row">
        <input type="checkbox" id="s_ftb"> <label for="s_ftb">First-time buyer</label>
      </div>
      <div class="check-row">
        <input type="checkbox" id="s_additional"> <label for="s_additional">Additional property (2nd home / BTL)</label>
      </div>
      <button class="btn" onclick="calcStamp()">Calculate</button>
      <div id="s_results" class="results"></div>
    </div>
  </div>

  <!-- AFFORDABILITY -->
  <div id="afford" class="panel">
    <div class="card">
      <h2>Affordability Checker</h2>
      <p style="color:var(--muted);margin-bottom:16px">Checks income multiples, repayment ratios, and BoE stress test (+3%).</p>
      <div class="form-grid">
        <div class="field">
          <label>Combined Annual Income</label>
          <input type="number" id="a_income" value="60000" step="1000">
        </div>
        <div class="field">
          <label>Loan Amount</label>
          <input type="number" id="a_loan" value="270000" step="5000">
        </div>
        <div class="field">
          <label>Interest Rate (%)</label>
          <input type="number" id="a_rate" value="5.75" step="0.1">
        </div>
        <div class="field">
          <label>Mortgage Term (years)</label>
          <input type="number" id="a_term" value="25">
        </div>
      </div>
      <button class="btn" onclick="calcAfford()">Check</button>
      <div id="a_results" class="results"></div>
    </div>
  </div>

  <!-- PURCHASE COSTS -->
  <div id="costs" class="panel">
    <div class="card">
      <h2>Full Purchase Cost Breakdown</h2>
      <div class="form-grid">
        <div class="field">
          <label>Property Price</label>
          <input type="number" id="c_price" value="300000" step="5000">
        </div>
        <div class="field">
          <label>Deposit %</label>
          <input type="number" id="c_deposit" value="10" min="5" max="100">
        </div>
        <div class="field">
          <label>Solicitor Fees</label>
          <input type="number" id="c_solicitor" value="1500">
        </div>
        <div class="field">
          <label>Survey Cost</label>
          <input type="number" id="c_survey" value="500">
        </div>
        <div class="field">
          <label>Broker Fee</label>
          <input type="number" id="c_broker" value="500">
        </div>
      </div>
      <div class="check-row">
        <input type="checkbox" id="c_ftb"> <label for="c_ftb">First-time buyer</label>
      </div>
      <button class="btn" onclick="calcCosts()">Calculate</button>
      <div id="c_results" class="results"></div>
    </div>
  </div>

  <!-- AREA PRICES -->
  <div id="area" class="panel">
    <div class="card">
      <h2>Area Sold Prices (Land Registry)</h2>
      <p style="color:var(--muted);margin-bottom:16px">Recent sold prices from HM Land Registry. Enter a postcode prefix or town.</p>
      <div class="form-grid">
        <div class="field">
          <label>Postcode Prefix (e.g. BS1, SW1A)</label>
          <input type="text" id="lr_postcode" placeholder="e.g. BS1">
        </div>
        <div class="field">
          <label>Or Town Name</label>
          <input type="text" id="lr_town" placeholder="e.g. Bristol">
        </div>
      </div>
      <button class="btn" onclick="calcArea()">Search</button>
      <div id="lr_results" class="results"></div>
    </div>
  </div>

  <!-- PROPERTY FEEDS -->
  <div id="feeds" class="panel">
    <div class="card">
      <h2>Property Feeds (Live House Search)</h2>
      <p style="color:var(--muted);margin-bottom:8px">Search live property listings from Zoopla &amp; Nestoria to find houses for sale.</p>
      <p style="color:var(--muted);margin-bottom:16px;font-size:0.85rem" id="pf_sources"></p>
      <div class="form-grid">
        <div class="field">
          <label>Location (town / city / postcode)</label>
          <input type="text" id="pf_location" placeholder="e.g. Bristol" value="London">
        </div>
        <div class="field">
          <label>Min Price (optional)</label>
          <input type="number" id="pf_min_price" placeholder="e.g. 200000">
        </div>
        <div class="field">
          <label>Max Price (optional)</label>
          <input type="number" id="pf_max_price" placeholder="e.g. 500000">
        </div>
        <div class="field">
          <label>Min Bedrooms (optional)</label>
          <input type="number" id="pf_min_beds" placeholder="e.g. 2" min="0" max="10">
        </div>
        <div class="field">
          <label>Property Type</label>
          <select id="pf_type">
            <option value="">Any</option>
            <option value="detached">Detached</option>
            <option value="semi-detached">Semi-detached</option>
            <option value="terraced">Terraced</option>
            <option value="flat">Flat / Apartment</option>
            <option value="bungalow">Bungalow</option>
          </select>
        </div>
        <div class="field">
          <label>Keywords (optional)</label>
          <input type="text" id="pf_keywords" placeholder="e.g. garden garage">
        </div>
        <div class="field">
          <label>Max Results</label>
          <input type="number" id="pf_max_results" value="20" min="5" max="50">
        </div>
      </div>
      <div style="display:flex;gap:8px;flex-wrap:wrap">
        <button class="btn" onclick="searchFeeds()">Search Properties</button>
        <button class="btn" onclick="feedStats()" style="background:var(--surface2);color:var(--accent)">Area Stats</button>
      </div>
      <div id="pf_results" class="results"></div>
    </div>
  </div>

</div>

<script>
const fmt = n => '£' + Number(n).toLocaleString('en-GB');
const pct = n => Number(n).toFixed(2) + '%';

function showTab(id) {
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.getElementById(id).classList.add('active');
  event.target.classList.add('active');
}

// Deposit slider live update
const depSlider = document.getElementById('m_deposit');
depSlider.addEventListener('input', () => {
  const v = depSlider.value;
  document.getElementById('m_dep_label').textContent = v + '%';
  const price = parseInt(document.getElementById('m_price').value) || 0;
  document.getElementById('m_dep_val').textContent = fmt(Math.round(price * v / 100));
});
document.getElementById('m_price').addEventListener('input', () => {
  const price = parseInt(document.getElementById('m_price').value) || 0;
  document.getElementById('m_dep_val').textContent = fmt(Math.round(price * depSlider.value / 100));
});

async function api(endpoint, params) {
  const q = new URLSearchParams(params).toString();
  const r = await fetch('/api/' + endpoint + '?' + q);
  return r.json();
}

async function calcMortgage() {
  const d = await api('mortgage', {
    price: document.getElementById('m_price').value,
    deposit: depSlider.value,
    term: document.getElementById('m_term').value,
    rate_type: document.getElementById('m_rate_type').value,
  });
  document.getElementById('m_results').innerHTML = `
    <div class="result-grid">
      <div class="stat"><div class="label">Monthly Payment</div><div class="value accent">${fmt(d.monthly)}</div></div>
      <div class="stat"><div class="label">Loan Amount</div><div class="value">${fmt(d.loan)}</div></div>
      <div class="stat"><div class="label">Interest Rate</div><div class="value">${pct(d.rate)}</div>
        <div class="sub">Base ${pct(d.base_rate)} + Spread ${pct(d.spread)} + LTV ${pct(d.ltv_premium)}</div></div>
      <div class="stat"><div class="label">Total Interest</div><div class="value red">${fmt(d.total_interest)}</div></div>
      <div class="stat"><div class="label">Total Repaid</div><div class="value">${fmt(d.total_repaid)}</div></div>
      <div class="stat"><div class="label">Deposit</div><div class="value green">${fmt(d.deposit)}</div>
        <div class="sub">${d.deposit_pct}%</div></div>
    </div>`;
}

async function calcDeposit() {
  const d = await api('deposit_comparison', {
    price: document.getElementById('d_price').value,
    term: document.getElementById('d_term').value,
  });
  let rows = d.map(r => `<tr class="${r.deposit_pct == 10 ? 'highlight' : ''}">
    <td>${r.deposit_pct}%</td><td class="num">${fmt(r.deposit)}</td>
    <td class="num">${fmt(r.loan)}</td><td class="num">${pct(r.rate)}</td>
    <td class="num" style="font-weight:700">${fmt(r.monthly)}</td>
    <td class="num" style="color:var(--red)">${fmt(r.total_interest)}</td></tr>`).join('');
  document.getElementById('d_results').innerHTML = `<table>
    <tr><th>Deposit</th><th>Amount</th><th>Loan</th><th>Rate</th><th>Monthly</th><th>Total Interest</th></tr>
    ${rows}</table>`;
}

async function calcStamp() {
  const d = await api('stamp_duty', {
    price: document.getElementById('s_price').value,
    ftb: document.getElementById('s_ftb').checked,
    additional: document.getElementById('s_additional').checked,
  });
  let bands = d.breakdown.map(b => `<tr><td>${b[0]}</td><td class="num">${fmt(b[1])}</td></tr>`).join('');
  document.getElementById('s_results').innerHTML = `
    <div class="result-grid">
      <div class="stat"><div class="label">Stamp Duty</div><div class="value accent">${fmt(d.stamp_duty)}</div></div>
      <div class="stat"><div class="label">Effective Rate</div><div class="value">${pct(d.effective_rate)}</div></div>
    </div>
    <table style="margin-top:16px"><tr><th>Band</th><th>Tax</th></tr>${bands}</table>`;
}

async function calcAfford() {
  const d = await api('affordability', {
    income: document.getElementById('a_income').value,
    loan: document.getElementById('a_loan').value,
    rate: document.getElementById('a_rate').value,
    term: document.getElementById('a_term').value,
  });
  const overall = d.passes_affordability && d.passes_stress ? 'pass' : 'fail';
  document.getElementById('a_results').innerHTML = `
    <div class="result-grid">
      <div class="stat"><div class="label">Result</div><div class="value ${overall}">${overall.toUpperCase()}</div></div>
      <div class="stat"><div class="label">Max Borrowing (4.5x)</div><div class="value">${fmt(d.max_borrowing)}</div></div>
      <div class="stat"><div class="label">Monthly Payment</div><div class="value accent">${fmt(d.monthly)}</div>
        <div class="sub">${d.ratio}% of income</div></div>
      <div class="stat"><div class="label">Stress Test @ ${pct(d.stress_rate)}</div>
        <div class="value ${d.passes_stress ? 'green' : 'red'}">${fmt(d.stress_monthly)}</div>
        <div class="sub">${d.stress_ratio}% of income</div></div>
    </div>`;
}

async function calcCosts() {
  const d = await api('purchase_costs', {
    price: document.getElementById('c_price').value,
    deposit: document.getElementById('c_deposit').value,
    ftb: document.getElementById('c_ftb').checked,
    solicitor: document.getElementById('c_solicitor').value,
    survey: document.getElementById('c_survey').value,
    broker: document.getElementById('c_broker').value,
  });
  let rows = Object.entries(d.breakdown).map(([k,v]) =>
    `<tr${k==='TOTAL'?' style="font-weight:700;color:var(--accent)"':''}><td>${k}</td><td class="num">${v}</td></tr>`).join('');
  document.getElementById('c_results').innerHTML = `
    <div class="result-grid">
      <div class="stat"><div class="label">Total Cash Needed</div><div class="value accent">${fmt(d.total_upfront)}</div></div>
    </div>
    <table style="margin-top:16px"><tr><th>Item</th><th>Cost</th></tr>${rows}</table>`;
}

async function calcArea() {
  const pc = document.getElementById('lr_postcode').value;
  const town = document.getElementById('lr_town').value;
  if (!pc && !town) { alert('Enter a postcode or town'); return; }
  document.getElementById('lr_results').innerHTML = '<div class="loading"><div class="spinner"></div> Querying Land Registry...</div>';
  const d = await api('area_prices', { postcode: pc, town: town });
  if (d.count === 0) {
    document.getElementById('lr_results').innerHTML = '<p style="color:var(--yellow);margin-top:16px">No data found. Try a different postcode or town.</p>';
    return;
  }
  let typeRows = '';
  if (d.by_type) {
    typeRows = Object.entries(d.by_type).map(([t,v]) =>
      `<tr><td>${t}</td><td class="num">${v.count}</td><td class="num">${fmt(v.avg)}</td><td class="num">${fmt(v.min)} — ${fmt(v.max)}</td></tr>`).join('');
  }
  document.getElementById('lr_results').innerHTML = `
    <div class="result-grid">
      <div class="stat"><div class="label">Sales Found</div><div class="value">${d.count}</div></div>
      <div class="stat"><div class="label">Average</div><div class="value accent">${fmt(d.mean)}</div></div>
      <div class="stat"><div class="label">Median</div><div class="value">${fmt(d.median)}</div></div>
      <div class="stat"><div class="label">Range</div><div class="value" style="font-size:1rem">${fmt(d.min)} — ${fmt(d.max)}</div></div>
    </div>
    ${typeRows ? `<table style="margin-top:16px"><tr><th>Type</th><th>Count</th><th>Average</th><th>Range</th></tr>${typeRows}</table>` : ''}`;
}

async function searchFeeds() {
  const loc = document.getElementById('pf_location').value;
  if (!loc) { alert('Enter a location'); return; }
  document.getElementById('pf_results').innerHTML = '<div class="loading"><div class="spinner"></div> Searching property portals...</div>';
  const d = await api('feeds/search', {
    location: loc,
    min_price: document.getElementById('pf_min_price').value,
    max_price: document.getElementById('pf_max_price').value,
    min_bedrooms: document.getElementById('pf_min_beds').value,
    property_type: document.getElementById('pf_type').value,
    keywords: document.getElementById('pf_keywords').value,
    max_results: document.getElementById('pf_max_results').value,
  });

  if (!d.listings || d.listings.length === 0) {
    document.getElementById('pf_results').innerHTML = `<p style="color:var(--yellow);margin-top:16px">${d.message || 'No properties found. Try broadening your search.'}</p>`;
    return;
  }

  let rows = d.listings.map((l,i) => `<tr>
    <td class="num" style="color:var(--muted)">${i+1}</td>
    <td>${l.bedrooms || '?'}</td>
    <td class="num" style="color:var(--green)">${l.price}</td>
    <td>${esc(l.type) || '—'}</td>
    <td><a href="${l.url}" target="_blank" style="color:var(--accent);text-decoration:none">${esc(l.address)}</a></td>
    <td style="color:var(--muted)">${esc(l.agent) || '—'}</td>
    <td style="color:var(--muted)">${l.source}</td>
  </tr>`).join('');

  let priceInfo = '';
  if (d.prices && d.prices.mean) {
    priceInfo = `
      <div class="result-grid" style="margin-bottom:16px">
        <div class="stat"><div class="label">Properties Found</div><div class="value">${d.count}</div></div>
        <div class="stat"><div class="label">Avg Price</div><div class="value accent">${fmt(d.prices.mean)}</div></div>
        <div class="stat"><div class="label">Median Price</div><div class="value">${fmt(d.prices.median)}</div></div>
        <div class="stat"><div class="label">Price Range</div><div class="value" style="font-size:1rem">${fmt(d.prices.min)} — ${fmt(d.prices.max)}</div></div>
      </div>`;
  }

  document.getElementById('pf_results').innerHTML = priceInfo +
    `<table><tr><th>#</th><th>Beds</th><th>Price</th><th>Type</th><th>Address</th><th>Agent</th><th>Source</th></tr>${rows}</table>`;
}

async function feedStats() {
  const loc = document.getElementById('pf_location').value;
  if (!loc) { alert('Enter a location'); return; }
  document.getElementById('pf_results').innerHTML = '<div class="loading"><div class="spinner"></div> Fetching property market data...</div>';
  const d = await api('feeds/stats', { location: loc });

  if (!d.count || d.count === 0) {
    document.getElementById('pf_results').innerHTML = `<p style="color:var(--yellow);margin-top:16px">${d.message || 'No data found. Try a different location.'}</p>`;
    return;
  }

  let html = '';

  // Price summary
  const p = d.prices || {};
  if (p.mean) {
    html += `<div class="result-grid">
      <div class="stat"><div class="label">Properties Found</div><div class="value">${d.count}</div></div>
      <div class="stat"><div class="label">Avg Price</div><div class="value accent">${fmt(p.mean)}</div></div>
      <div class="stat"><div class="label">Median</div><div class="value">${fmt(p.median)}</div></div>
      <div class="stat"><div class="label">Range</div><div class="value" style="font-size:1rem">${fmt(p.min)} — ${fmt(p.max)}</div></div>
    </div>`;
  } else {
    html += `<div class="result-grid">
      <div class="stat"><div class="label">Properties Found</div><div class="value">${d.count}</div></div>
    </div>`;
  }

  // Property type breakdown
  if (d.by_type && Object.keys(d.by_type).length) {
    let typeRows = Object.entries(d.by_type).map(([t, v]) =>
      `<tr><td>${esc(t)}</td><td class="num">${v.count}</td><td class="num" style="color:var(--green)">${v.avg_price ? fmt(v.avg_price) : '—'}</td>
       <td class="num">${v.min_price && v.max_price ? fmt(v.min_price)+' — '+fmt(v.max_price) : '—'}</td></tr>`).join('');
    html += `<h3 style="color:var(--accent);margin:16px 0 8px">By Property Type</h3>
      <table><tr><th>Type</th><th>Count</th><th>Avg Price</th><th>Range</th></tr>${typeRows}</table>`;
  }

  // Bedroom breakdown
  if (d.by_bedrooms && Object.keys(d.by_bedrooms).length) {
    let bedRows = Object.entries(d.by_bedrooms).map(([b, v]) =>
      `<tr><td>${esc(b)}</td><td class="num">${v.count}</td><td class="num" style="color:var(--green)">${v.avg_price ? fmt(v.avg_price) : '—'}</td></tr>`).join('');
    html += `<h3 style="color:var(--accent);margin:16px 0 8px">By Bedrooms</h3>
      <table><tr><th>Bedrooms</th><th>Count</th><th>Avg Price</th></tr>${bedRows}</table>`;
  }

  // Top agents
  if (d.top_agents && d.top_agents.length) {
    let agentRows = d.top_agents.map(a =>
      `<tr><td>${esc(a.name)}</td><td class="num">${a.listings}</td></tr>`).join('');
    html += `<h3 style="color:var(--accent);margin:16px 0 8px">Top Estate Agents</h3>
      <table><tr><th>Agent</th><th>Listings</th></tr>${agentRows}</table>`;
  }

  // Sample listings
  if (d.sample_listings && d.sample_listings.length) {
    let sampleRows = d.sample_listings.map(l =>
      `<tr><td><a href="${l.url}" target="_blank" style="color:var(--accent);text-decoration:none">${esc(l.address)}</a></td>
       <td class="num" style="color:var(--green)">${l.price}</td><td>${l.bedrooms || '?'}</td>
       <td>${esc(l.type) || '—'}</td><td style="color:var(--muted)">${esc(l.agent) || '—'}</td></tr>`).join('');
    html += `<h3 style="color:var(--accent);margin:16px 0 8px">Sample Listings</h3>
      <table><tr><th>Address</th><th>Price</th><th>Beds</th><th>Type</th><th>Agent</th></tr>${sampleRows}</table>`;
  }

  document.getElementById('pf_results').innerHTML = html;
}

function esc(s) { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; }

// Check configured property sources on load
(async () => {
  try {
    const s = await api('feeds/sources', {});
    let parts = [];
    if (s.zoopla) parts.push('Zoopla ✓');
    else parts.push('Zoopla ✗ (set ZOOPLA_API_KEY)');
    if (s.nestoria) parts.push('Nestoria ✓ (free)');
    const el = document.getElementById('pf_sources');
    if (el) el.textContent = 'Sources: ' + parts.join(' | ');
  } catch(e) {}
})();

// Auto-calculate mortgage on load
calcMortgage();
</script>
</body>
</html>
"""


# --- API ROUTES ---

@app.route('/')
def index():
    return render_template_string(HTML, base_rate=BASE_RATE)


@app.route('/api/mortgage')
def api_mortgage():
    r = calculate_mortgage(
        int(request.args.get('price', 300000)),
        float(request.args.get('deposit', 10)),
        int(request.args.get('term', 25)),
        request.args.get('rate_type', 'average_fixed_2yr'),
        BASE_RATE,
    )
    return jsonify(
        monthly=round(r.monthly_repayment, 2),
        loan=r.loan_amount,
        rate=round(r.interest_rate, 2),
        base_rate=round(r.base_rate, 2),
        spread=round(r.lender_spread, 2),
        ltv_premium=round(r.ltv_premium, 2),
        total_interest=round(r.total_interest),
        total_repaid=round(r.total_repayment),
        deposit=r.deposit_amount,
        deposit_pct=round(r.deposit_percent, 1),
    )


@app.route('/api/deposit_comparison')
def api_deposit():
    results = deposit_comparison(
        int(request.args.get('price', 300000)),
        int(request.args.get('term', 25)),
    )
    return jsonify([
        dict(
            deposit_pct=round(r.deposit_percent),
            deposit=r.deposit_amount,
            loan=r.loan_amount,
            rate=round(r.interest_rate, 2),
            monthly=round(r.monthly_repayment),
            total_interest=round(r.total_interest),
        )
        for r in results
    ])


@app.route('/api/stamp_duty')
def api_stamp():
    r = calculate_stamp_duty(
        int(request.args.get('price', 300000)),
        request.args.get('ftb', 'false').lower() == 'true',
        request.args.get('additional', 'false').lower() == 'true',
    )
    return jsonify(
        stamp_duty=r.stamp_duty,
        effective_rate=round(r.effective_rate, 2),
        breakdown=r.breakdown,
    )


@app.route('/api/affordability')
def api_afford():
    r = check_affordability(
        int(request.args.get('income', 60000)),
        int(request.args.get('loan', 270000)),
        float(request.args.get('rate', 5.75)),
        int(request.args.get('term', 25)),
    )
    return jsonify(
        passes_affordability=r.passes_affordability,
        passes_stress=r.passes_stress_test,
        max_borrowing=r.max_borrowing,
        monthly=round(r.monthly_repayment),
        ratio=round(r.repayment_to_income, 1),
        stress_rate=round(r.stress_test_rate, 2),
        stress_monthly=round(r.stress_test_monthly),
        stress_ratio=round(r.stress_test_ratio, 1),
    )


@app.route('/api/purchase_costs')
def api_costs():
    r = total_purchase_cost(
        int(request.args.get('price', 300000)),
        float(request.args.get('deposit', 10)),
        request.args.get('ftb', 'false').lower() == 'true',
        int(request.args.get('solicitor', 1500)),
        int(request.args.get('survey', 500)),
        int(request.args.get('broker', 500)),
    )
    return jsonify(r)


@app.route('/api/area_prices')
def api_area():
    pc = request.args.get('postcode', '').strip() or None
    town = request.args.get('town', '').strip() or None
    r = area_price_stats(pc or town or '', '2023-01-01')
    return jsonify(r)


@app.route('/api/feeds/sources')
def api_feed_sources():
    return jsonify(feeds_sources_configured())


@app.route('/api/feeds/search')
def api_feed_search():
    criteria = PropertySearchCriteria(
        location=request.args.get('location', '').strip(),
        min_price=int(request.args['min_price']) if request.args.get('min_price') else None,
        max_price=int(request.args['max_price']) if request.args.get('max_price') else None,
        min_bedrooms=int(request.args['min_bedrooms']) if request.args.get('min_bedrooms') else None,
        property_type=request.args.get('property_type', '').strip(),
        keywords=request.args.get('keywords', '').strip(),
        max_results=min(int(request.args.get('max_results', 20)), 50),
    )

    listings = search_property_feeds(criteria)

    # Compute price stats from results
    prices = [l.price for l in listings if l.price and l.price > 0]
    price_stats = {}
    if prices:
        sorted_p = sorted(prices)
        n = len(sorted_p)
        price_stats = {
            "count_with_price": n,
            "min": sorted_p[0],
            "max": sorted_p[-1],
            "mean": round(sum(sorted_p) / n),
            "median": sorted_p[n // 2],
        }

    return jsonify(
        count=len(listings),
        prices=price_stats,
        listings=[
            {
                "title": l.title,
                "address": l.address,
                "price": l.price_display,
                "bedrooms": l.bedrooms,
                "bathrooms": l.bathrooms,
                "type": l.property_type or "",
                "agent": l.agent_name or "",
                "url": l.url,
                "image_url": l.image_url,
                "source": l.source,
            }
            for l in listings
        ],
        sources=feeds_sources_configured(),
    )


@app.route('/api/feeds/stats')
def api_feed_stats():
    location = request.args.get('location', '').strip()
    if not location:
        return jsonify(count=0, message="Location is required")
    r = area_property_stats(location)
    return jsonify(r)


if __name__ == '__main__':
    import webbrowser, threading
    print("\n  House Buyer Tool")
    print("  Open: http://localhost:5000\n")
    threading.Timer(1.0, lambda: webbrowser.open('http://localhost:5000')).start()
    app.run(debug=False, port=5000)
