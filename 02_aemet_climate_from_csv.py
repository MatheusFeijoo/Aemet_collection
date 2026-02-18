import requests
import csv
import json
import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
)

logger = logging.getLogger(__name__)

AEMET_BASE_URL = "https://opendata.aemet.es/opendata/api"
AEMET_DAILY_ENDPOINT = f"{AEMET_BASE_URL}/valores/climatologicos/diarios/datos"
MAX_DAYS_PER_REQUEST = 180
RATE_LIMIT_DELAY = 0.8
REQUEST_TIMEOUT = 30

ALL_PROVINCES = [
    ("01", "Álava"), ("02", "Albacete"), ("03", "Alicante"), ("04", "Almería"),
    ("05", "Ávila"), ("06", "Badajoz"), ("07", "Islas Baleares"), ("08", "Barcelona"),
    ("09", "Burgos"), ("10", "Cáceres"), ("11", "Cádiz"), ("12", "Castellón"),
    ("13", "Ciudad Real"), ("14", "Córdoba"), ("15", "Coruña"), ("16", "Cuenca"),
    ("17", "Girona"), ("18", "Granada"), ("19", "Guadalajara"), ("20", "Gipuzkoa"),
    ("21", "Huelva"), ("22", "Huesca"), ("23", "Jaén"), ("24", "León"),
    ("25", "Lleida"), ("26", "Lugo"), ("28", "Madrid"), ("29", "Málaga"),
    ("30", "Murcia"), ("31", "Navarra"), ("32", "Ourense"), ("33", "Asturias"),
    ("34", "Palencia"), ("35", "Las Palmas"), ("36", "Pontevedra"), ("37", "La Rioja"),
    ("40", "Segovia"), ("41", "Sevilla"), ("42", "Soria"), ("43", "Tarragona"),
    ("44", "Teruel"), ("45", "Toledo"), ("46", "Valencia"), ("47", "Valladolid"),
    ("48", "Bizkaia"), ("49", "Zamora"), ("50", "Zaragoza"), ("51", "Ceuta"), ("52", "Melilla")
]

def create_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def find_latest_station_csv():
    csv_files = sorted(Path('.').glob('aemet_stations_*.csv'))
    if not csv_files:
        logger.error("No station CSV files found. Run aemet_fetch_station_inventory.py first")
        return None
    
    latest = csv_files[-1]
    logger.info(f"Using station CSV: {latest}")
    return str(latest)


def load_stations_from_csv(csv_filename, province_filter=None):
    logger.info(f"Loading stations from {csv_filename}...")
    
    stations = {}  # Use dict keyed by station_id for fast lookup
    
    try:
        with open(csv_filename, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            
            for row in reader:
                # Skip if no station ID
                if not row.get('station_id'):
                    continue
                
                # Filter by province if specified
                if province_filter and row.get('province_code') != province_filter:
                    continue
                
                stations[row['station_id']] = row
        
        logger.info(f"Loaded {len(stations)} stations")
        if province_filter and stations:
            first_station = list(stations.values())[0]
            logger.info(f"Province: {first_station['province_name']} ({province_filter})")
        
        return stations
        
    except Exception as e:
        logger.error(f"Error loading CSV: {e}")
        return None


def split_date_range(start_date, end_date, max_days=MAX_DAYS_PER_REQUEST):
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as e:
        logger.error(f"Invalid date format: {e}")
        return []
    
    windows = []
    current_start = start
    
    while current_start < end:
        current_end = current_start + timedelta(days=max_days)
        if current_end > end:
            current_end = end
        
        windows.append((
            current_start.strftime("%Y-%m-%d"),
            current_end.strftime("%Y-%m-%d")
        ))
        
        current_start = current_end + timedelta(days=1)
    
    logger.info(f"Date range split into {len(windows)} window(s)")
    return windows


def fetch_station_climate_data(session, station_id, start_date, end_date, api_key):
    start_ts = f"{start_date}T00:00:00UTC"
    end_ts = f"{end_date}T23:59:59UTC"
    
    url = f"{AEMET_DAILY_ENDPOINT}/fechaini/{start_ts}/fechafin/{end_ts}/estacion/{station_id}/"
    
    try:
        logger.debug(f"Fetching {station_id} ({start_date} to {end_date})")
        time.sleep(RATE_LIMIT_DELAY)
        
        # First request: Get the data URL
        response = session.get(url, params={"api_key": api_key}, timeout=REQUEST_TIMEOUT)
        
        if response.status_code == 404:
            logger.debug(f"Station {station_id} not found (404)")
            return None
        
        if response.status_code != 200:
            logger.debug(f"HTTP {response.status_code} for {station_id}")
            return None
        
        data = response.json()
        
        if data.get('estado') != 200:
            logger.debug(f"API error status {data.get('estado')} for {station_id}")
            return None
        
        # Extract data URL from response
        datos_url = data.get('datos')
        if not datos_url:
            logger.debug(f"No datos URL in response for {station_id}")
            return None
        
        # Second request: Fetch actual data from S3 URL
        logger.debug(f"Fetching data from {datos_url[:50]}...")
        time.sleep(RATE_LIMIT_DELAY)
        
        response = session.get(datos_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        
        records = response.json()
        
        # Ensure it's a list
        if not isinstance(records, list):
            records = [records] if records else []
        
        logger.debug(f"Retrieved {len(records)} records for {station_id}")
        return records
        
    except Exception as e:
        logger.debug(f"Error fetching {station_id}: {e}")
        return None


def convert_european_number(value_str):
    if value_str is None or value_str == '' or value_str == 'Nulo':
        return None
    
    try:
        # Replace comma with dot for European format
        normalized = str(value_str).replace(',', '.')
        return float(normalized)
    except (ValueError, TypeError):
        return None


def normalize_record(raw_record, station_info):
    try:
        date = raw_record.get('fecha')
        if not date:
            return None
        
        # Extract clean date (remove time if present)
        if 'T' in str(date):
            date = str(date).split('T')[0]
        
        # CORRECTED: Use actual field names from API response
        record = {
            'date': date,
            'station_id': raw_record.get('indicativo', ''),
            'station_name': raw_record.get('nombre', ''),
            'province_code': station_info.get('province_code', ''),
            'province_name': raw_record.get('provincia', station_info.get('province_name', '')),
            'latitude': station_info.get('latitude', ''),
            'longitude': station_info.get('longitude', ''),
            'altitude': convert_european_number(raw_record.get('altitud')),
            
            # Temperature fields (CORRECTED field names)
            'tmax': convert_european_number(raw_record.get('tmax')),
            'tmin': convert_european_number(raw_record.get('tmin')),
            'tmed': convert_european_number(raw_record.get('tmed')),  # Average temp
            
            # Precipitation
            'precipitation': convert_european_number(raw_record.get('prec')),
            
            # Wind (CORRECTED field names)
            'wind_direction': convert_european_number(raw_record.get('dir')),
            'wind_speed': convert_european_number(raw_record.get('velmedia')),
            'wind_gust': convert_european_number(raw_record.get('racha')),
            
            # Sunshine
            'sunshine_hours': convert_european_number(raw_record.get('sol')),
            
            # Pressure (CORRECTED: use presMax/presMin)
            'pressure_max': convert_european_number(raw_record.get('presMax')),
            'pressure_min': convert_european_number(raw_record.get('presMin')),
            
            # Humidity (CORRECTED: use hrMedia/hrMax/hrMin)
            'humidity_avg': convert_european_number(raw_record.get('hrMedia')),
            'humidity_max': convert_european_number(raw_record.get('hrMax')),
            'humidity_min': convert_european_number(raw_record.get('hrMin')),
        }
        
        return record
        
    except Exception as e:
        logger.debug(f"Error normalizing record: {e}")
        return None


def collect_climate_data(api_key, csv_filename, province_filter, start_date, end_date):
    logger.info("=" * 70)
    logger.info("AEMET Climate Data Collection Started (CORRECTED - Actual API Format)")
    logger.info(f"Station CSV: {csv_filename}")
    if province_filter:
        logger.info(f"Province filter: {province_filter}")
    logger.info(f"Period: {start_date} to {end_date}")
    logger.info("=" * 70)
    
    session = create_session()
    all_records = []
    failed_stations = []
    successful_count = 0
    total_count = 0
    
    try:
        # Load stations from CSV
        stations = load_stations_from_csv(csv_filename, province_filter)
        
        if not stations:
            raise RuntimeError(f"No stations found in {csv_filename}")
        
        total_count = len(stations)
        logger.info(f"Processing {total_count} stations...\n")
        
        # Split date range
        windows = split_date_range(start_date, end_date)
        
        if not windows:
            raise RuntimeError("Invalid date range")
        
        # Fetch data for each station and window
        for idx, (station_id, station_info) in enumerate(stations.items(), 1):
            station_name = station_info['station_name']
            
            logger.info(f"[{idx}/{total_count}] {station_id:8} - {station_name}")
            
            station_records = 0
            windows_with_data = 0
            
            for win_idx, (window_start, window_end) in enumerate(windows, 1):
                try:
                    records = fetch_station_climate_data(
                        session,
                        station_id,
                        window_start,
                        window_end,
                        api_key
                    )
                    
                    if not records:
                        continue
                    
                    # Normalize each record
                    for raw_record in records:
                        normalized = normalize_record(raw_record, station_info)
                        if normalized:
                            all_records.append(normalized)
                            station_records += 1
                    
                    windows_with_data += 1
                    
                except Exception as e:
                    logger.debug(f"  Error processing window {win_idx}/{len(windows)}: {e}")
                    continue
            
            if station_records > 0:
                logger.info(f"  ✓ Collected {station_records:5} records ({windows_with_data}/{len(windows)} windows)")
                successful_count += 1
            else:
                logger.warning(f"  ✗ No records for {station_id}")
                failed_stations.append({'station_id': station_id, 'station_name': station_name})
        
        # Deduplicate and sort
        unique_records = list({(r['date'], r['station_id']): r for r in all_records}.values())
        unique_records.sort(key=lambda r: (r['station_id'], r['date']))
        
        logger.info("\n" + "=" * 70)
        logger.info(f"[OK] Total unique records collected: {len(unique_records)}")
        logger.info(f"[OK] Successful stations: {successful_count}/{total_count}")
        logger.info(f"[OK] Failed stations: {len(failed_stations)}/{total_count}")
        logger.info("=" * 70 + "\n")
        
        return unique_records, successful_count, total_count, failed_stations
        
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        raise
    finally:
        session.close()


def export_to_json(records, filename):
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump({
            'summary': {
                'total_records': len(records),
                'unique_dates': len(set(r['date'] for r in records)),
                'unique_stations': len(set(r['station_id'] for r in records)),
                'collection_timestamp': datetime.utcnow().isoformat() + 'Z'
            },
            'data': records
        }, f, indent=2, ensure_ascii=False)
    
    logger.info(f"[OK] JSON exported to {filename}")


def export_to_csv(records, filename):
    if not records:
        logger.warning("No records to export")
        return
    
    fieldnames = list(records[0].keys())
    
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    
    logger.info(f"[OK] CSV exported to {filename}")


def print_summary(records, successful, total, failed):
    print("\n" + "=" * 70)
    print("COLLECTION SUMMARY")
    print("=" * 70)
    print(f"Total Stations:      {total}")
    print(f"Successful Stations: {successful}")
    print(f"Failed Stations:     {len(failed)}")
    print(f"Total Records:       {len(records):,}")
    
    if records:
        unique_dates = len(set(r['date'] for r in records))
        unique_stations = len(set(r['station_id'] for r in records))
        date_min = min(r['date'] for r in records)
        date_max = max(r['date'] for r in records)
        
        print(f"Unique Dates:        {unique_dates}")
        print(f"Unique Stations:     {unique_stations}")
        print(f"Date Range:          {date_min} to {date_max}")
        
        # Show sample record to verify format
        print(f"\nSample record (first):")
        sample = records[0]
        print(f"  Date: {sample['date']}")
        print(f"  Station: {sample['station_id']} - {sample['station_name']}")
        print(f"  Temp Max: {sample['tmax']}°C")
        print(f"  Temp Min: {sample['tmin']}°C")
        print(f"  Precipitation: {sample['precipitation']} mm")
    
    print(f"Collection Time:     {datetime.now().isoformat()}")
    
    if failed:
        print("\nFailed Stations:")
        for failure in failed[:10]:
            print(f"  - {failure['station_id']} ({failure['station_name']})")
        if len(failed) > 10:
            print(f"  ... and {len(failed) - 10} more")
    
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
    
    # OPTION 1: Single province
    # province_code = "20"  # 20 = Gipuzkoa (16 stations)
    
    # OPTION 2: Multiple provinces
    # province_code = ["01", "20", "48"]  # Basque Country
    
    # OPTION 3: All 52 Spanish provinces
    province_code = "ALL"  # Uncomment to collect all provinces
    
    # Date range
    start_date = "2013-01-01"
    end_date = "2024-12-31"
    
    # Output formats
    output_format = "both"  # "json", "csv", or "both"
    
    # ============================================================================
    # QUICK PROVINCE REFERENCE
    # ============================================================================
    # 01=Álava, 02=Albacete, 03=Alicante, 04=Almería, 05=Ávila, 06=Badajoz
    # 07=Islas Baleares, 08=Barcelona, 09=Burgos, 10=Cáceres, 11=Cádiz, 12=Castellón
    # 13=Ciudad Real, 14=Córdoba, 15=Coruña, 16=Cuenca, 17=Girona, 18=Granada
    # 19=Guadalajara, 20=Gipuzkoa, 21=Huelva, 22=Huesca, 23=Jaén, 24=León
    # 25=Lleida, 26=Lugo, 28=Madrid, 29=Málaga, 30=Murcia, 31=Navarra
    # 32=Ourense, 33=Asturias, 34=Palencia, 35=Las Palmas, 36=Pontevedra, 37=La Rioja
    # 40=Segovia, 41=Sevilla, 42=Soria, 43=Tarragona, 44=Teruel, 45=Toledo
    # 46=Valencia, 47=Valladolid, 48=Bizkaia, 49=Zamora, 50=Zaragoza, 51=Ceuta, 52=Melilla
    
    try:
        # Find latest station CSV
        csv_filename = find_latest_station_csv()
        if not csv_filename:
            raise RuntimeError("Cannot proceed without station CSV")
        
        # Handle province selection
        if isinstance(province_code, str):
            if province_code.upper() == "ALL":
                # Collect all provinces
                logger.info(f"\n{'='*70}")
                logger.info(f"COLLECTING DATA FOR ALL 52 SPANISH PROVINCES")
                logger.info(f"{'='*70}\n")
                
                all_results = {}
                total_records = 0
                
                for idx, (code, name) in enumerate(ALL_PROVINCES, 1):
                    logger.info(f"\n[{idx}/{len(ALL_PROVINCES)}] {name} ({code})")
                    
                    try:
                        records, successful, total, failed = collect_climate_data(
                            api_key=api_key,
                            csv_filename=csv_filename,
                            province_filter=code,
                            start_date=start_date,
                            end_date=end_date
                        )
                        
                        # Export results
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        csv_file = f"aemet_climate_{code}_{name}_{timestamp}.csv"
                        json_file = f"aemet_climate_{code}_{name}_{timestamp}.json"
                        
                        export_to_csv(records, csv_file)
                        export_to_json(records, json_file)
                        print_summary(records, successful, total, failed)
                        
                        all_results[name] = {
                            'code': code,
                            'records': len(records),
                            'csv': csv_file,
                            'json': json_file,
                            'status': 'success'
                        }
                        total_records += len(records)
                        
                    except Exception as e:
                        logger.error(f"Error collecting {name}: {e}")
                        all_results[name] = {'code': code, 'status': 'error', 'error': str(e)}
                
                # Print final summary
                logger.info(f"\n{'='*70}")
                logger.info("FINAL SUMMARY - ALL PROVINCES")
                logger.info(f"{'='*70}")
                successful_count = sum(1 for r in all_results.values() if r.get('status') == 'success')
                failed_count = sum(1 for r in all_results.values() if r.get('status') == 'error')
                logger.info(f"Provinces: {successful_count} successful, {failed_count} failed")
                logger.info(f"Total records collected: {total_records:,}")
                logger.info(f"{'='*70}\n")
                
            else:
                # Single province
                records, successful, total, failed = collect_climate_data(
                    api_key=api_key,
                    csv_filename=csv_filename,
                    province_filter=province_code,
                    start_date=start_date,
                    end_date=end_date
                )
                
                # Export results
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                
                if output_format in ["json", "both"]:
                    json_file = f"aemet_climate_{timestamp}.json"
                    export_to_json(records, json_file)
                
                if output_format in ["csv", "both"]:
                    csv_file = f"aemet_climate_{timestamp}.csv"
                    export_to_csv(records, csv_file)
                
                # Print summary
                print_summary(records, successful, total, failed)
        
        else:
            # Multiple provinces (list)
            all_results = {}
            total_records = 0
            
            for idx, code in enumerate(province_code, 1):
                # Find province name
                prov_name = next((name for c, name in ALL_PROVINCES if c == code), code)
                logger.info(f"\n[{idx}/{len(province_code)}] {prov_name} ({code})")
                
                try:
                    records, successful, total, failed = collect_climate_data(
                        api_key=api_key,
                        csv_filename=csv_filename,
                        province_filter=code,
                        start_date=start_date,
                        end_date=end_date
                    )
                    
                    # Export results
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    csv_file = f"aemet_climate_{code}_{prov_name}_{timestamp}.csv"
                    json_file = f"aemet_climate_{code}_{prov_name}_{timestamp}.json"
                    
                    export_to_csv(records, csv_file)
                    export_to_json(records, json_file)
                    print_summary(records, successful, total, failed)
                    
                    all_results[prov_name] = {
                        'code': code,
                        'records': len(records),
                        'csv': csv_file,
                        'json': json_file,
                        'status': 'success'
                    }
                    total_records += len(records)
                    
                except Exception as e:
                    logger.error(f"Error collecting {prov_name}: {e}")
                    all_results[prov_name] = {'code': code, 'status': 'error', 'error': str(e)}
            
            # Print final summary
            logger.info(f"\n{'='*70}")
            logger.info("FINAL SUMMARY - MULTIPLE PROVINCES")
            logger.info(f"{'='*70}")
            successful_count = sum(1 for r in all_results.values() if r.get('status') == 'success')
            failed_count = sum(1 for r in all_results.values() if r.get('status') == 'error')
            logger.info(f"Provinces: {successful_count} successful, {failed_count} failed")
            logger.info(f"Total records collected: {total_records:,}")
            logger.info(f"{'='*70}\n")
        
        logger.info("[OK] Collection completed successfully")
        return 0
        
    except Exception as e:
        logger.critical(f"Fatal error: {e}")
        import traceback
        logger.critical(traceback.format_exc())
        return 1


if __name__ == "__main__":
    exit(main())