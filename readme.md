# AEMET Climate Data Collector

A two-step Python pipeline to fetch and store historical daily climate data from all Spanish weather stations via the [AEMET OpenData API](https://opendata.aemet.es).

## Overview

The pipeline consists of two scripts that must be run in order:

1. **`01_aemet_fetch_station_inventory.py`** — Downloads the full AEMET station inventory and saves it as a local CSV/JSON file.
2. **`02_aemet_climate_from_csv.py`** — Reads that station inventory and fetches historical daily climate records for one province, a list of provinces, or all 52 Spanish provinces.

---

## Requirements

- Python 3.8+
- `requests`
- `urllib3`

---

## Setup

### 1. Get an AEMET API Key

Register at [AEMET OpenData](https://opendata.aemet.es/centrodedescargas/inicio) to obtain a free API key.

### 2. Save the API Key

Create a file named `aemet_api_key.txt` in the project root and paste your key inside:

---

## Usage

### Step 1 — Fetch Station Inventory

```bash
python 01_aemet_fetch_station_inventory.py
```

This script:
- Calls the AEMET inventory endpoint for all stations in Spain.
- Normalises province names (handles accents, bilingual names such as *Araba/Álava*, *Gipuzkoa*, *Bizkaia*, etc.).
- Exports two files timestamped at runtime:
  - `aemet_stations_YYYYMMDD_HHMMSS.csv`
  - `aemet_stations_YYYYMMDD_HHMMSS.json`
- Writes a log to `aemet_station_fetch.log`.

**CSV columns:** `station_id`, `station_name`, `province_code`, `province_name`, `latitude`, `longitude`, `altitude`

---

### Step 2 — Fetch Climate Data

```bash
python 02_aemet_climate_from_csv.py
```

Edit the configuration block in `main()` before running:

```python
# OPTION 1: Single province
province_code = "20"          # 20 = Gipuzkoa

# OPTION 2: Multiple provinces (Basque Country)
province_code = ["01", "20", "48"]

# OPTION 3: All 52 Spanish provinces
province_code = "ALL"

# Date range
start_date = "2013-01-01"
end_date   = "2024-12-31"

# Output format: "json", "csv", or "both"
output_format = "both"
```

The script automatically:
- Detects the latest `aemet_stations_*.csv` file produced in Step 1.
- Splits long date ranges into 180-day windows (API limit).
- Applies rate-limiting (0.8 s between requests) and retries on 429/5xx errors.
- Deduplicates records before export.

**Output files** (per province when running `ALL`):
- `aemet_climate_<code>_<province>_<timestamp>.csv`
- `aemet_climate_<code>_<province>_<timestamp>.json`

---

## Output Schema

Each climate record contains the following fields:

| Field | Description | Unit |
|---|---|---|
| `date` | Observation date | `YYYY-MM-DD` |
| `station_id` | AEMET station identifier | — |
| `station_name` | Station name | — |
| `province_code` | INE province code (2 digits) | — |
| `province_name` | Province name | — |
| `latitude` / `longitude` | Coordinates | Decimal degrees |
| `altitude` | Station elevation | m |
| `tmax` / `tmin` / `tmed` | Max / min / mean temperature | °C |
| `precipitation` | Daily precipitation | mm |
| `wind_speed` | Mean wind speed (`velmedia`) | km/h |
| `wind_gust` | Maximum wind gust (`racha`) | km/h |
| `wind_direction` | Wind direction (`dir`) | Degrees (0–360) |
| `sunshine_hours` | Daily sunshine hours (`sol`) | h |
| `pressure_max` / `pressure_min` | Atmospheric pressure | hPa |
| `humidity_avg` / `humidity_max` / `humidity_min` | Relative humidity | % |

> European decimal commas returned by the API (e.g. `"12,4"`) are automatically converted to floats. Missing or `"Nulo"` values are stored as `null` / empty.

---

## Province Reference

| Code | Province | Code | Province |
|---|---|---|---|
| 01 | Álava | 28 | Madrid |
| 02 | Albacete | 29 | Málaga |
| 03 | Alicante | 30 | Murcia |
| 07 | Islas Baleares | 31 | Navarra |
| 08 | Barcelona | 35 | Las Palmas |
| 11 | Cádiz | 41 | Sevilla |
| 15 | Coruña | 46 | Valencia |
| 20 | Gipuzkoa | 48 | Bizkaia |
| 26 | La Rioja | 50 | Zaragoza |
| 27 | Lugo | 51 | Ceuta |

Full list of all 52 province codes is embedded in both scripts.

---

## Notes

- The AEMET OpenData API is **free** but rate-limited. For a full national collection (`"ALL"`) expect several hours of runtime.
- The API uses a two-step redirect pattern: a first call returns a signed S3 URL, and a second call downloads the actual data.
- Requests are retried automatically up to 3 times with exponential backoff on transient errors (429, 500–504).
- All text files are written in **UTF-8** to correctly handle Spanish characters.

---

## License

MIT
```

***

A few things worth noting about the README structure: [ppl-ai-file-upload.s3.amazonaws](https://ppl-ai-file-upload.s3.amazonaws.com/web/direct-files/attachments/60660547/9a50c42f-77de-499c-9094-2ff6c44f9178/02_aemet_climate_from_csv.py)

- The **output schema table** maps all normalised field names (like `velmedia` → `wind_speed`) so downstream users don't need to reverse-engineer the code.
- The **`.gitignore` reminder** for `aemet_api_key.txt` mirrors what both scripts already enforce — they abort if the file is missing.
- The **project structure tree** reflects the actual runtime-generated filenames (`aemet_stations_*`, `aemet_climate_*`) exactly as the scripts produce them.

Feel free to add a `## Contributing` section or a badge block (build status, license) at the top if you plan to make the repo public.