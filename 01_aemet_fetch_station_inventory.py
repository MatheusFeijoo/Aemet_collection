import unicodedata
import requests
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('aemet_station_fetch.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


PROVINCE_NAME_MAP = {
    # 01 - Álava (Basque: Araba)
    "ARABA":          ("01", "Álava"),
    "ÁLAVA":          ("01", "Álava"),
    "ALAVA":          ("01", "Álava"),
    "ARABA/ÁLAVA":    ("01", "Álava"),
    "ARABA/ALAVA":    ("01", "Álava"),
    # 02 - Albacete
    "ALBACETE":       ("02", "Albacete"),
    # 03 - Alicante
    "ALICANTE":           ("03", "Alicante"),
    "ALICANTE/ALACANT":   ("03", "Alicante"),
    "ALACANT":            ("03", "Alicante"),
    # 04 - Almería
    "ALMERÍA":        ("04", "Almería"),
    "ALMERIA":        ("04", "Almería"),
    # 05 - Ávila
    "ÁVILA":          ("05", "Ávila"),
    "AVILA":          ("05", "Ávila"),
    # 06 - Badajoz
    "BADAJOZ":        ("06", "Badajoz"),
    # 07 - Islas Baleares
    "ISLAS BALEARES": ("07", "Islas Baleares"),
    "ILLES BALEARS":  ("07", "Islas Baleares"),
    "BALEARES":       ("07", "Islas Baleares"),
    "BALEARS":        ("07", "Islas Baleares"),
    # 08 - Barcelona
    "BARCELONA":      ("08", "Barcelona"),
    # 09 - Burgos
    "BURGOS":         ("09", "Burgos"),
    # 10 - Cáceres
    "CÁCERES":        ("10", "Cáceres"),
    "CACERES":        ("10", "Cáceres"),
    # 11 - Cádiz
    "CÁDIZ":          ("11", "Cádiz"),
    "CADIZ":          ("11", "Cádiz"),
    # 12 - Castellón
    "CASTELLÓN":            ("12", "Castellón"),
    "CASTELLON":            ("12", "Castellón"),
    "CASTELLÓ":             ("12", "Castellón"),
    "CASTELLO":             ("12", "Castellón"),
    "CASTELLÓN/CASTELLÓ":   ("12", "Castellón"),
    "CASTELLON/CASTELLO":   ("12", "Castellón"),
    # 13 - Ciudad Real
    "CIUDAD REAL":    ("13", "Ciudad Real"),
    # 14 - Córdoba
    "CÓRDOBA":        ("14", "Córdoba"),
    "CORDOBA":        ("14", "Córdoba"),
    # 15 - A Coruña
    "CORUÑA":         ("15", "Coruña"),
    "A CORUÑA":       ("15", "Coruña"),
    "LA CORUÑA":      ("15", "Coruña"),
    "A CORUNA":       ("15", "Coruña"),
    # 16 - Cuenca
    "CUENCA":         ("16", "Cuenca"),
    # 17 - Girona
    "GIRONA":         ("17", "Girona"),
    "GERONA":         ("17", "Girona"),
    # 18 - Granada
    "GRANADA":        ("18", "Granada"),
    # 19 - Guadalajara
    "GUADALAJARA":    ("19", "Guadalajara"),
    # 20 - Gipuzkoa
    "GUIPÚZCOA":      ("20", "Gipuzkoa"),
    "GUIPUZCOA":      ("20", "Gipuzkoa"),
    "GUIPUZKOA":      ("20", "Gipuzkoa"),
    "GIPUZKOA":       ("20", "Gipuzkoa"),
    "GIPUZKOAO":      ("20", "Gipuzkoa"),
    # 21 - Huelva
    "HUELVA":         ("21", "Huelva"),
    # 22 - Huesca
    "HUESCA":         ("22", "Huesca"),
    # 23 - Jaén
    "JAÉN":           ("23", "Jaén"),
    "JAEN":           ("23", "Jaén"),
    # 24 - León
    "LEÓN":           ("24", "León"),
    "LEON":           ("24", "León"),
    # 25 - Lleida
    "LLEIDA":         ("25", "Lleida"),
    "LÉRIDA":         ("25", "Lleida"),
    "LERIDA":         ("25", "Lleida"),
    # 26 - La Rioja
    "LA RIOJA":       ("26", "La Rioja"),
    "RIOJA":          ("26", "La Rioja"),
    # 27 - Lugo
    "LUGO":           ("27", "Lugo"),
    # 28 - Madrid
    "MADRID":         ("28", "Madrid"),
    # 29 - Málaga
    "MÁLAGA":         ("29", "Málaga"),
    "MALAGA":         ("29", "Málaga"),
    # 30 - Murcia
    "MURCIA":         ("30", "Murcia"),
    # 31 - Navarra
    "NAVARRA":        ("31", "Navarra"),
    "NAFARROA":       ("31", "Navarra"),
    # 32 - Ourense
    "OURENSE":        ("32", "Ourense"),
    "ORENSE":         ("32", "Ourense"),
    # 33 - Asturias
    "ASTURIAS":       ("33", "Asturias"),
    # 34 - Palencia
    "PALENCIA":       ("34", "Palencia"),
    # 35 - Las Palmas
    "LAS PALMAS":     ("35", "Las Palmas"),
    "PALMAS":         ("35", "Las Palmas"),
    # 36 - Pontevedra
    "PONTEVEDRA":     ("36", "Pontevedra"),
    # 37 - Salamanca
    "SALAMANCA":      ("37", "Salamanca"),
    # 38 - Santa Cruz de Tenerife
    "SANTA CRUZ DE TENERIFE": ("38", "Santa Cruz de Tenerife"),
    "STA. CRUZ DE TENERIFE":  ("38", "Santa Cruz de Tenerife"),
    "S.C. TENERIFE":          ("38", "Santa Cruz de Tenerife"),
    "TENERIFE":               ("38", "Santa Cruz de Tenerife"),
    # 39 - Cantabria
    "CANTABRIA":      ("39", "Cantabria"),
    "SANTANDER":      ("39", "Cantabria"),
    # 40 - Segovia
    "SEGOVIA":        ("40", "Segovia"),
    # 41 - Sevilla
    "SEVILLA":        ("41", "Sevilla"),
    # 42 - Soria
    "SORIA":          ("42", "Soria"),
    # 43 - Tarragona
    "TARRAGONA":      ("43", "Tarragona"),
    # 44 - Teruel
    "TERUEL":         ("44", "Teruel"),
    # 45 - Toledo
    "TOLEDO":         ("45", "Toledo"),
    # 46 - Valencia
    "VALENCIA":       ("46", "Valencia"),
    "VALÈNCIA":       ("46", "Valencia"),
    # 47 - Valladolid
    "VALLADOLID":     ("47", "Valladolid"),
    # 48 - Bizkaia
    "VIZCAYA":              ("48", "Bizkaia"),
    "VIZCAYA/BIZKAIA":      ("48", "Bizkaia"),
    "VIZCAYA/BIZCAIA":      ("48", "Bizkaia"),
    "BIZKAIA":              ("48", "Bizkaia"),
    "BIZCAIA":              ("48", "Bizkaia"),
    # 49 - Zamora
    "ZAMORA":         ("49", "Zamora"),
    # 50 - Zaragoza
    "ZARAGOZA":       ("50", "Zaragoza"),
    # 51 - Ceuta
    "CEUTA":          ("51", "Ceuta"),
    # 52 - Melilla
    "MELILLA":        ("52", "Melilla"),
}


def _strip_accents(text: str) -> str:
    """Remove diacritics and return uppercase ASCII-folded string."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    ).upper()


_PROVINCE_MAP_NORMALIZED = {
    _strip_accents(k): v for k, v in PROVINCE_NAME_MAP.items()
}


def normalize_province(province_name):
    if not province_name:
        return None, None

    key = _strip_accents(province_name.strip())

    if key in _PROVINCE_MAP_NORMALIZED:
        return _PROVINCE_MAP_NORMALIZED[key]

    for map_key, value in _PROVINCE_MAP_NORMALIZED.items():
        if map_key in key or key in map_key:
            return value

    logger.warning(f"Province '{province_name}' not recognised — station will have empty province_code")
    return None, None


def fetch_station_inventory(api_key):
    logger.info("=" * 70)
    logger.info("AEMET Station Inventory Fetch Started")
    logger.info("=" * 70)

    url = "https://opendata.aemet.es/opendata/api/valores/climatologicos/inventarioestaciones/todasestaciones"
    try:
        logger.info("Requesting station inventory from AEMET...")
        response = requests.get(url, params={"api_key": api_key}, timeout=30)
        response.raise_for_status()
        data = response.json()

        if data.get('estado') != 200:
            raise RuntimeError(f"AEMET API error: status {data.get('estado')}")

        datos_url = data.get('datos')
        if not datos_url:
            raise RuntimeError("No datos URL in response")

        logger.info(f"Fetching station data from {datos_url[:60]}...")
        response = requests.get(datos_url, timeout=30)
        response.raise_for_status()
        stations = response.json()

        if not isinstance(stations, list):
            stations = [stations] if stations else []

        logger.info(f"Received {len(stations)} stations from API")
        return stations

    except Exception as e:
        logger.critical(f"Error fetching station inventory: {e}")
        raise


def process_stations(raw_stations):
    logger.info("Processing station data...")
    processed = []
    skipped = 0
    normalized_provinces = {}

    for idx, station in enumerate(raw_stations, 1):
        try:
            station_id   = station.get('indicativo', '')
            station_name = station.get('nombre', '')
            latitude     = station.get('latitud', '')
            longitude    = station.get('longitud', '')
            altitude     = station.get('altitud', '')
            province_raw = station.get('provincia', '')

            if not station_id or not station_name:
                skipped += 1
                continue

            province_code, province_name = normalize_province(province_raw)

            if not province_code:
                province_code = ""
                province_name = province_raw

            if province_code not in normalized_provinces:
                normalized_provinces[province_code] = province_name

            processed.append({
                'station_id':    station_id,
                'station_name':  station_name,
                'province_code': province_code,
                'province_name': province_name,
                'latitude':      latitude,
                'longitude':     longitude,
                'altitude':      altitude,
            })

            if idx % 100 == 0:
                logger.info(f"  Processed {idx} stations...")

        except Exception as e:
            logger.warning(f"Error processing station {idx}: {e}")
            skipped += 1
            continue

    logger.info(f"Processed {len(processed)} stations (skipped {skipped})")
    logger.info(f"Provinces found: {len(normalized_provinces)}")
    return processed, normalized_provinces


def export_to_csv(stations, filename):
    if not stations:
        logger.warning("No stations to export")
        return

    fieldnames = ['station_id', 'station_name', 'province_code', 'province_name',
                  'latitude', 'longitude', 'altitude']
    try:
        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(stations)
        logger.info(f"[OK] CSV exported to {filename}")
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}")
        raise


def export_to_json(stations, filename):
    if not stations:
        logger.warning("No stations to export")
        return

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump({
                'summary': {
                    'total_stations':       len(stations),
                    'unique_provinces':     len(set(s['province_code'] for s in stations)),
                    'collection_timestamp': datetime.utcnow().isoformat() + 'Z'
                },
                'stations': stations
            }, f, indent=2, ensure_ascii=False)
        logger.info(f"[OK] JSON exported to {filename}")
    except Exception as e:
        logger.error(f"Error exporting JSON: {e}")
        raise


def print_summary(stations, normalized_provinces):
    print("\n" + "=" * 70)
    print("STATION INVENTORY SUMMARY")
    print("=" * 70)
    print(f"Total Stations   : {len(stations)}")
    print(f"Unique Provinces : {len(normalized_provinces)}")
    print("\nProvinces found:")
    for code in sorted(normalized_provinces.keys()):
        name  = normalized_provinces[code]
        count = sum(1 for s in stations if s['province_code'] == code)
        print(f"  {code:>2} - {name:35} ({count} stations)")
    print("=" * 70 + "\n")


def main():
    # Load API key from file (keep aemet_api_key.txt out of version control)
    key_file = Path("aemet_api_key.txt")
    if not key_file.exists():
        logger.critical("aemet_api_key.txt not found. Create it with your AEMET API key.")
        return 1
    api_key = key_file.read_text(encoding="utf-8").strip()
    if not api_key:
        logger.critical("aemet_api_key.txt is empty.")
        return 1
    logger.info("API key loaded from aemet_api_key.txt")

    try:
        raw_stations = fetch_station_inventory(api_key)
        processed_stations, normalized_provinces = process_stations(raw_stations)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_file  = f"aemet_stations_{timestamp}.csv"
        json_file = f"aemet_stations_{timestamp}.json"

        export_to_csv(processed_stations, csv_file)
        export_to_json(processed_stations, json_file)
        print_summary(processed_stations, normalized_provinces)

        logger.info("[OK] Station inventory fetch completed successfully")
        return 0

    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        import traceback
        logger.critical(traceback.format_exc())
        return 1


if __name__ == "__main__":
    exit(main())