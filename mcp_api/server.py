"""
CNRA Groundwater MCP Server
---------------------------
This MCP server provides tools to query California's groundwater data
via the CNRA CKAN API. It abstracts complex resource IDs into simple,
queryable Python functions for AI agents.

Author: Hanieh Haeri (hhaeri0911@gmail.com)
"""

from mcp.server.fastmcp import FastMCP
import httpx
import json
# from analytics import run_data_qa_logic
# from visualization import generate_interactive_hydrograph_logic



# Define the dictionary as a centralized constant
DATA_DICTIONARY = {
    "stations": {
        "description": "Metadata for groundwater monitoring stations.",
        "columns": ["site_code", "well_name", "latitude", "longitude", "gse", "rpe", "basin_code", "basin_name", "well_depth", "well_use", "well_type"]},
    "measurements": {
        "description": "Historical groundwater level time-series data.",
        "columns": ["site_code", "msmt_date", "wlm_rpe", "wlm_gse", "gwe", "gse_gwe"]},
    "perforations":{
        "description": "Well Perforation data.",
        "columns": ["site_code", "top_prf_int", "bot_prf_int"]},
    "gsp_monitoring": {
        "description": "GSP representative well monitoring data.",
        "columns": ["SITE_CODE", "WELL_NAME", "BASIN_NAME", "GSP_NAME", "MONITORING_NETWORK_TYPE", "SUSTAINABILITY_INDICATORS", "PRINCIPAL_AQUIFER", "SMC_START_DATE",
        "SMC_MT", "SMC_IM_5_YR", "SMC_IM_10_YR", "SMC_IM_15_YR", "SMC_MO", "FIRST_MSMT_DATE", "LAST_MSMT_DATE", "MSMT_COUNT"]}
}

# Initialize the MCP server with a clear description
mcp = FastMCP("CNRA-Groundwater-Tool")
# mcp = FastMCP(
#     "CNRA-Groundwater-Tool",
#     description=(f"HydroAgent Groundwater API. Schema: {DATA_DICTIONARY}"
#                 "IMPORTANT: Always join datasets using the 'site_code' column. "
#                 "The 'site_code' is the primary key for all station and measurement tables."))

# CKAN API Configuration
# CKAN Endpoints
SEARCH_URL = "https://data.cnra.ca.gov/api/3/action/datastore_search"
SQL_URL = "https://data.cnra.ca.gov/api/3/action/datastore_search_sql"

RESOURCES = {
    "stations": "af157380-fb42-4abf-b72a-6f9f98868077",
    "measurements": "bfa9f262-24a1-45bd-8dc8-138bc8107266",
    "perforations": "f1deaa6d-2cb5-4052-a73f-08a69f26b750",
    "gsp_monitoring": "38dc5a77-0428-4d8b-970a-51797ed2cd36",
}

def get_cnra_client():
    """Generates a pre-configured HTTP client disguised as a Mac Chrome browser."""
    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    # Return a client with all our required safety bypasses built-in
    return httpx.AsyncClient(
        timeout=60.0, 
        headers=browser_headers, 
        verify=False
    )

async def fetch_ckan_paginated(resource_key: str, filters: dict, chunk_size: int = 5000) -> list:
    """
    Universal pagination helper for standard CKAN Datastore Search queries.
    Uses query parameters (limit/offset) to exhaust the endpoint.
    """
    all_records = []
    current_offset = 0
    filters_str = json.dumps(filters) if filters else "{}"

    # 1. Create a fake browser identity
    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    async with get_cnra_client() as client:
        while True:
            params = {
                "resource_id": RESOURCES[resource_key], 
                "filters": filters_str,
                "limit": chunk_size,
                "offset": current_offset
            }
            
            response = await client.get(SEARCH_URL, params=params)
            response.raise_for_status()
            
            chunk = response.json()["result"]["records"]
            if not chunk:
                break
                
            all_records.extend(chunk)
            
            if len(chunk) < chunk_size:
                break
                
            current_offset += chunk_size

    return all_records

async def execute_sql_paginated(base_sql: str, chunk_size: int = 10000) -> list:
    """
    Universal pagination helper for CKAN Datastore SQL queries.
    Dynamically injects LIMIT and OFFSET into the SQL string to exhaust the endpoint.
    """
    all_records = []
    current_offset = 0

    while True:
        # Append the pagination commands to the base SQL string
        paginated_sql = f"{base_sql} LIMIT {chunk_size} OFFSET {current_offset}"
        chunk = await execute_sql(paginated_sql)
        
        if not chunk:
            break
            
        all_records.extend(chunk)
        
        if len(chunk) < chunk_size:
            break
            
        current_offset += chunk_size

    return all_records

async def fetch_ckan(resource_key: str, filters: dict):
    """
    Helper function to perform standardized, paginated requests to the CKAN Data API.

    Args:
        resource_key: The internal key for the target resource.
        filters: A dictionary of key-value pairs to filter the query.
    """
    async with get_cnra_client() as client:
        params = {"resource_id": RESOURCES[resource_key], "filters": json.dumps(filters) if filters else "{}"}
        response = await client.get(SEARCH_URL, params=params)
        response.raise_for_status()
        return response.json()["result"]["records"]

async def execute_sql(sql_query: str) -> list:
    """Helper to execute SQL queries against the CKAN DataStore."""
    async with get_cnra_client() as client:
        params = {"sql": sql_query}
        response = await client.get(SQL_URL, params=params)
        response.raise_for_status()
        return response.json()["result"]["records"]

@mcp.tool()
async def get_water_years() -> list:
    """
    Fetches the official California Water Year classifications dynamically 
    from the data.ca.gov CKAN API (Paginated).
    """
    url = "https://data.ca.gov/api/3/action/datastore_search"
    resource_id = "105614f4-c71d-4191-b1f9-ea510afd8b62"
    
    all_records = []
    current_offset = 0
    chunk_size = 5000

    async with get_cnra_client() as client:
        while True:
            params = {"resource_id": resource_id, "limit": chunk_size, "offset": current_offset}
            response = await client.get(url, params=params)
            response.raise_for_status()
            
            chunk = response.json()["result"]["records"]
            if not chunk: break
            
            all_records.extend(chunk)
            if len(chunk) < chunk_size: break
            
            current_offset += chunk_size

    return all_records

@mcp.tool()
async def get_dataset_columns(resource_key: str) -> list:
    """
    Returns the list of available column names for a given dataset.
    Use this if you are unsure about column names or receive a database error.
    """
    # This query asks the database itself for its schema
    sql = f'SELECT column_name FROM information_schema.columns WHERE table_name = \'{RESOURCES[resource_key]}\''
    return await execute_sql(sql)


@mcp.tool()
async def get_perforation_data(site_code: str):
    """
    Retrieves well perforation (screened interval) details for a station.

    Use this to understand the specific depth intervals from which the well
    draws groundwater, which is critical for SGMA regulatory analysis.

    Args:
        site_code: The unique identifier for the groundwater station.
    """
    return await fetch_ckan_paginated("perforations", {"site_code": site_code})

@mcp.tool()
async def get_station_info(site_code: str):
    """
    Fetches comprehensive metadata for a specific groundwater monitoring station.
    Use this to retrieve geographical coordinates, basin names, station status,
    and physical attributes of the well.

    Args:
        site_code: The unique identifier for the groundwater station (e.g., '374828N1211757W001').
    """
    return await fetch_ckan_paginated("stations", {"site_code": site_code})

@mcp.tool()
async def get_stations_in_basin(basin_name: str) -> list:
    """Fetches all stations within a groundwater basin using SQL."""
    sql = f'SELECT * FROM "{RESOURCES["stations"]}" WHERE "basin_name" = \'{basin_name}\''
    return await execute_sql_paginated(sql)

# Targeted Retrieval and Spatial Exploration

@mcp.tool()
async def get_stations_in_area(min_lat: float, min_lon: float, max_lat: float, max_lon: float) -> list:
    """Fetches all stations within a rectangular bounding box using SQL."""
    sql = (
        f'SELECT * FROM "{RESOURCES["stations"]}" '
        f'WHERE "latitude" > {min_lat} AND "latitude" < {max_lat} '
        f'AND "longitude" > {min_lon} AND "longitude" < {max_lon}'
    )
    return await execute_sql_paginated(sql)

@mcp.tool()
async def get_stations_by_attribute(attribute: str, value: str) -> list:
    """
    Queries groundwater monitoring stations by any valid database column attribute.

    Selected Supported attributes:
    - site_code: Location based 18-char alphanumeric code.
    - basin_code: DWR Bulletin 118 Basin-Subbasin Code.
    - basin_name: DWR Bulletin 118 Basin-Subbasin Name.
    - county_name: County Name.
    - well_type: Type of well (e.g., Monitoring, Production).
    - well_use: Purpose of the well.
    - monitoring_program: DWR monitoring program the well is primarily monitored under.

    Args:
        attribute: The database column name (e.g., 'basin_name').
        value: The specific value to filter for (e.g., 'SANTA CLARA VALLEY').
    """
    sql = f'SELECT * FROM "{RESOURCES["stations"]}" WHERE "{attribute}" = \'{value}\''
    return await execute_sql_paginated(sql)

@mcp.tool()
async def query_dataset(resource_key: str, filters: dict, columns: list = None) -> list:
    """
    Executes a flexible query against a dataset using multiple filter criteria.
    Supported resources: {list(DATA_DICTIONARY.keys())}

    Args:
        resource_key: The target dataset ('stations', 'measurements', etc.)
        filters: A dictionary of column names and values for filtering (e.g., {'site_code': 'X', 'year': '2025'})
        columns: Optional list of specific columns to return (e.g., ['date', 'water_level']).
    """
    # 1. Handle Column Projection (The "Select" part)
    select_clause = ", ".join([f'"{c}"' for c in columns]) if columns else "*"
    # 2. Dynamically build WHERE clause
    where_clauses = [f'"{k}" = \'{v}\'' for k, v in filters.items()]
    where_sql = " AND ".join(where_clauses) if where_clauses else "1=1" # Fallback if empty filters
    base_sql = f'SELECT {select_clause} FROM "{RESOURCES[resource_key]}" WHERE {where_sql}'
    
    # 3. Safely apply ordering ONLY if it is the measurements table
    if resource_key == "measurements":
        base_sql += ' ORDER BY "msmt_date" ASC'

    # 4. Delegate to the universal SQL paginator
    return await execute_sql_paginated(base_sql)

@mcp.tool()
async def get_records_by_attribute(resource_key: str, attribute: str, value: str) -> list:
    """
    Generic tool to query any registered dataset by a specific attribute.

    Args:
        resource_key: The dataset (e.g., 'stations', 'gsp_monitoring').
        attribute: The database column to filter by.
        value: The value to filter for.
    """
    sql = f'SELECT * FROM "{RESOURCES[resource_key]}" WHERE "{attribute}" = \'{value}\''
    return await execute_sql_paginated(sql)

@mcp.tool()
async def get_unique_values(resource_key: str, column_name: str, filter_column: str = None, filter_value: str = None) -> list:
    """
    Returns unique values from a specific column in any available dataset, optionally filtered by another attribute.
    Use this for hierarchical discovery (e.g., 'What are all basin names in this county?')
    Args:
        resource_key: The dataset (e.g., 'stations', 'measurements').
        column_name: The column to inspect.
        filter_column: Optional column to filter by (e.g., 'county_name').
        filter_value: Optional value for the filter (e.g., 'Alameda').
    """
    sql = f'SELECT DISTINCT "{column_name}" FROM "{RESOURCES[resource_key]}"'
    # Add optional WHERE clause
    if filter_column and filter_value:
        sql += f' WHERE "{filter_column}" = \'{filter_value}\''
    sql += f' ORDER BY "{column_name}"'

    return await execute_sql(sql)

@mcp.tool()
async def get_column_statistics(resource_key: str, column_name: str, filter_column: str = None, filter_value: str = None) -> list:
    """
    Computes summary statistics (count, min, max, avg) for a numeric column,
    optionally filtered by another attribute (e.g., site_code).

    Args:
        resource_key: The dataset (e.g., 'measurements').
        column_name: The numeric column to analyze.
        filter_column: Optional column to filter by (e.g., 'site_code').
        filter_value: Optional value for the filter (e.g., '374828N1211757W001').
    """
    # Base SQL
    sql = f"""
    SELECT
        COUNT("{column_name}") as total_count,
        MIN("{column_name}") as min_value,
        MAX("{column_name}") as max_value,
        AVG("{column_name}") as average_value
    FROM "{RESOURCES[resource_key]}"
    """

    # Add optional WHERE clause
    if filter_column and filter_value:
        sql += f' WHERE "{filter_column}" = \'{filter_value}\''

    return await execute_sql(sql)

### telemetry
@mcp.tool()
async def get_measurements(site_code: str, columns: list = None, start_date: str = None, end_date: str = None):
    """
    Retrieves historical periodic groundwater level measurements for a station with column selection.

site_code: Station identifier.
        columns: Optional list of columns to return (e.g., ['measurement_date', 'water_level']).
        start_date: Filter for data on or after (YYYY-MM-DD).
        end_date: Filter for data on or before (YYYY-MM-DD).
    """
    # Build SQL directly to support proper date range operators
    select_clause = ", ".join([f'"{c}"' for c in columns]) if columns else "*"
    base_sql = f'SELECT {select_clause} FROM "{RESOURCES["measurements"]}" WHERE "site_code" = \'{site_code}\''
    if start_date: base_sql += f' AND "msmt_date" >= \'{start_date}\''
    if end_date: base_sql += f' AND "msmt_date" <= \'{end_date}\''
    
    # Ensures chronological order before paginating
    base_sql += ' ORDER BY "msmt_date" ASC'
    
    # Delegate to the universal SQL paginator
    return await execute_sql_paginated(base_sql)

@mcp.tool()
async def get_annual_fall_lows(site_code: str) -> list:
    """
    Fetches the lowest annual groundwater elevation (GWE) during the fall season (Sept-Nov).

    This tool dynamically groups measurements by year and extracts the minimum
    value recorded within the Q4 window for robust SGMA trend assessment.

    Args:
        site_code: The unique identifier for the station.
    """
    # Using SQL date_part to capture Q4 (Sept, Oct, Nov)
    sql = f"""
    SELECT
        date_part('year', "msmt_date") as measurement_year,
        MIN("gwe") as fall_low_gwe
    FROM "{RESOURCES['measurements']}"
    WHERE "site_code" = '{site_code}'
    AND date_part('month', "msmt_date") IN (9, 10, 11)
    GROUP BY measurement_year
    ORDER BY measurement_year DESC
    """
    return await execute_sql(sql)

# @mcp.tool()
# async def run_data_qa(site_code: str) -> str:
#     """
#     Scans raw groundwater measurements for anomalies.
#     Applies corrections and saves the cleaned dataset.
#     """
#     # We pass the async fetch tools directly into the logic module
#     return await run_data_qa_logic(
#         site_code, 
#         get_measurements_func=get_measurements, 
#         get_records_func=get_records_by_attribute
#     )

# @mcp.tool()
# async def generate_interactive_hydrograph(site_code: str) -> str:
#     """
#     Generates an interactive Plotly hydrograph for a given site_code.
#     Awaits data from the CKAN API, calculates a 5-year moving average, 
#     and opens the HTML chart directly in the browser.
#     """
#     return await generate_interactive_hydrograph_logic(
#         site_code,
#         get_measurements_func=get_measurements,
#         get_records_func=get_records_by_attribute,
#         get_wy_func=get_water_years
#     )

if __name__ == "__main__":
    mcp.run()