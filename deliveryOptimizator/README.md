Delivery Optimizator

A practical, two-vehicle delivery route optimizer that:
- Geocodes depots and delivery addresses with Google Maps Geocoding API (with local caching).
- Assigns stops to two vehicles from two depots using a fast, balanced nearest‑neighbor heuristic.
- Reorders each vehicle’s stops using Google Distance Matrix + OR‑Tools TSP to minimize driving time.
- Prints readable summaries and saves per‑vehicle CSVs with per‑leg and cumulative totals.

This README explains how to set up, configure, and run the tool, plus the expected inputs/outputs and troubleshooting tips.

Contents
- Features
- Requirements
- Installation
- Configuration (.env)
- Input data format
- Running the optimizer
- Outputs
- Notes, limitations, and roadmap
- Troubleshooting

Features
- Two depots (two vehicles) supported out of the box.
- Local cache of geocoding results to reduce API calls.
- Chunked Distance Matrix usage to respect Google API element limits.
- CSV outputs with per‑leg distance/time and cumulative totals.

Requirements
- Python 3.9+ recommended
- Google Maps Platform API key with access to:
  - Geocoding API
  - Distance Matrix API
- System packages for OR‑Tools as required by your OS (pip package pulls binaries for most platforms)

Installation
1) Clone or extract the repository.
2) Create and activate a virtual environment (recommended).
3) Install dependencies:
   pip install -r deliveryOptimizator/requirements.txt

Configuration (.env)
Create a .env file at project root or in the working directory so python-dotenv can load it. Minimum required:
- GOOGLE_MAPS_API_KEY=your_real_key
Optional flags (read by deliveryOptimizator/config.py):
- USE_REAL_API=1            # 1=use Google APIs (default), 0=intended offline/mock mode (note: main path currently calls Google)
- FORCE_REFRESH=0           # future use: ignore caches when 1
- LOG_LEVEL=INFO
- MAX_API_REQUESTS_PER_DAY=950
- CACHE_DIR=deliveryOptimizator/data/cache
- VEHICLES=1                # currently ignored by the main entry; solver supports exactly 2 vehicles via two depots
- TIME_LIMIT_SECONDS=15     # OR-Tools time limit for TSP subproblem

Important: The current main flow requires GOOGLE_MAPS_API_KEY and calls Google APIs.

Input data format
Place CSVs under deliveryOptimizator/data/input/.
- depots.csv: exactly two rows, with at least an address column.
- deliveries.csv: one row per delivery address.
Headers accepted by the loader: address (required), name (optional). If name is missing, it generates Stop_#.

Examples
1) depots.csv
address
"Depot A full address"
"Depot B full address"

2) deliveries.csv
address
"Customer address 1"
"Customer address 2"
...

Running the optimizer
From the repository root or from the deliveryOptimizator directory:
- Ensure .env contains a valid GOOGLE_MAPS_API_KEY
- Ensure input files exist in deliveryOptimizator/data/input/
- Run:
  python deliveryOptimizator/main.py
The script will:
1) Load depots and deliveries.
2) Validate there are exactly two depots.
3) Geocode all addresses (using and updating data/cache/coords.json).
4) Build preliminary balanced routes (two vehicles).
5) For each vehicle, build a driving-time matrix and solve a TSP to reorder stops.
6) Print routes and totals in the console.
7) Export per‑vehicle CSVs to deliveryOptimizator/data/output/.

Outputs
- Console: human-readable routes per vehicle, with totals. Distances and durations are formatted.
- Files: one CSV per vehicle in deliveryOptimizator/data/output/ named like vehicle_1_YYYY-MM-DD_HH-MM.csv. Each file contains:
  - Columns: Stop, Address, Distance_km, TravelTime_min, Cumulative_km, Cumulative_min
  - A final Total row with cumulative sums.

Notes, limitations, and roadmap
- Two depots only: The current solver expects exactly two depots (and thus two vehicles). If you provide more or fewer, it exits with a clear message.
- Live Google APIs: The main flow currently requires online access to Geocoding and Distance Matrix and a valid API key.
- Caching: Geocoding results are cached at deliveryOptimizator/data/cache/coords.json.
- Distance matrix chunking: Requests are tiled (10x10) to stay within common per-request element caps.
For a deeper technical analysis, problems identified, and a proposed enhancement roadmap (offline mode, multi‑vehicle VRP, consolidated outputs, tests/CI), see deliveryOptimizator/ANALYSIS.md.

Troubleshooting
- Missing API key
  Symptom: ❌ ERROR: GOOGLE_MAPS_API_KEY is missing...
  Fix: Add GOOGLE_MAPS_API_KEY to your .env or environment, then re-run.

- Wrong number of depots
  Symptom: ❌ ERROR: This solver currently supports exactly 2 depots/vehicles.
  Fix: Ensure depots.csv has exactly two address rows.

- API quota or request errors
  Symptom: Distance Matrix/Geocoding failures or slow responses.
  Tips:
  - Verify billing and API enablement for Geocoding and Distance Matrix.
  - Reduce the batch size or number of deliveries.
  - Re-run later if hitting rate limits.

- Non‑ASCII characters in CSV
  The loader opens files with UTF‑8 encoding. Keep your CSVs in UTF‑8 and ensure quotes are balanced.

- Output distances/times look like zero for some legs
  The CSV export is fail‑soft: if a per‑leg Distance Matrix call fails, it writes zeros and continues. Totals printed earlier come from the TSP matrices and may be more reliable.

License
If not specified elsewhere, treat this as internal/use-at-your-own-risk. Add a proper license if you plan to distribute.
