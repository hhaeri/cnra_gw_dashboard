import dash
from dash import dcc, html, Input, Output, callback, State, no_update, clientside_callback, DiskcacheManager
import dash_bootstrap_components as dbc
from dash_extensions.javascript import Namespace
import dash_leaflet as dl
import pandas as pd
import asyncio
import gc  # MUST IMPORT GARBAGE COLLECTOR
import urllib.parse
import tempfile
import os
import shutil
import diskcache
import csv


# Import your server tools
from mcp_api.server import execute_sql_paginated, RESOURCES

# Create a temporary folder on the hard drive to manage background tasks
cache = diskcache.Cache("./cache")
background_callback_manager = DiskcacheManager(cache)

# Register as a page in the Multi-Page Application
dash.register_page(__name__, path='/')
# ==========================================
# 1. DATA CACHE & INITIALIZATION
# ==========================================
def load_master_network_cache():
    """
    Queries the live CNRA CKAN database via raw SQL using the paginator.
    Uses pure SELECT * to completely bypass state firewalls and CKAN quoting bugs,
    relying on Pandas for all downstream filtering and joining.
    """
    sql_stations = f'SELECT * FROM "{RESOURCES["stations"]}"'
    sql_gsp = f'SELECT * FROM "{RESOURCES["gsp_monitoring"]}"'
    
    async def fetch_both():
        task1 = execute_sql_paginated(sql_stations)
        task2 = execute_sql_paginated(sql_gsp)
        return await asyncio.gather(task1, task2)

    try:
        stations_records, gsp_records = asyncio.run(fetch_both())
        
        df_stations = pd.DataFrame(stations_records)
        df_gsp = pd.DataFrame(gsp_records)
        
        # INSTANT MEMORY NUKE: Delete the massive raw JSON lists and force clear RAM
        del stations_records
        del gsp_records
        gc.collect()

        if df_stations.empty:
            raise ValueError("The database returned an empty station dataset.")
            
        # NORMALIZE STATION COLUMNS
        df_stations.columns = [str(c).lower() for c in df_stations.columns]

        # --- PANDAS MEMORY SLICING ---
        desired_columns = [
            'site_code', 'well_name', 'latitude', 'longitude', 
            'county_name', 'basin_name', 'well_use', 'well_type', 'monitoring_program'
        ]
        
        valid_cols = [c for c in desired_columns if c in df_stations.columns]
        df_stations = df_stations[valid_cols]

        # Ensure fallbacks exist so the UI doesn't crash
        if 'well_name' not in df_stations.columns:
            df_stations['well_name'] = "Unknown Well"
        if 'county_name' not in df_stations.columns:
            df_stations['county_name'] = "Unknown County"
        if 'basin_name' not in df_stations.columns:
            df_stations['basin_name'] = "Unknown Basin"

        # Ensure coordinates are numeric for Leaflet mapping
        df_stations['latitude'] = pd.to_numeric(df_stations['latitude'], errors='coerce')
        df_stations['longitude'] = pd.to_numeric(df_stations['longitude'], errors='coerce')
        df_stations = df_stations.dropna(subset=['latitude', 'longitude'])
        
        # --- BULLETPROOF PANDAS JOIN ---
        if not df_gsp.empty:
            df_gsp.columns = [str(c).upper() for c in df_gsp.columns]

            if 'SITE_CODE' in df_gsp.columns:
                df_gsp = df_gsp.rename(columns={'SITE_CODE': 'site_code'})
            
            # 1. Ask Pandas to keep the SMC threshold columns 
            gsp_cols_to_keep = [
                'site_code', 'MONITORING_NETWORK_TYPE', 
                'SMC_MO', 'SMC_MT', 'SMC_IM_5_YR', 
                'SMC_IM_10_YR', 'SMC_IM_15_YR'
            ]

            # 2. Filter GSP columns to only the essential ones for the dashboard
            # This prevents memory bloat from unnecessary fields
            valid_gsp_cols = [c for c in gsp_cols_to_keep if c in df_gsp.columns]
            df_gsp = df_gsp[valid_gsp_cols]

            if 'MONITORING_NETWORK_TYPE' in df_gsp.columns:
                df = pd.merge(
                    df_stations, 
                    df_gsp, 
                    on='site_code', 
                    how='left'
                )
            else:
                df = df_stations.copy()
                df['MONITORING_NETWORK_TYPE'] = 'Non-Representative'
        else:
            df = df_stations.copy()
            df['MONITORING_NETWORK_TYPE'] = 'Non-Representative'
            
        # Sanitize the SGMA classifications
        df['MONITORING_NETWORK_TYPE'] = df['MONITORING_NETWORK_TYPE'].fillna('Non-Representative')
        df.loc[
            df['MONITORING_NETWORK_TYPE'] != 'SGMA Representative', 
            'MONITORING_NETWORK_TYPE'
        ] = 'Non-Representative'

        # ====================================================
        # --- MULTI-NODE WELL CONSTRUCTION LOGIC ---
        # ====================================================
        # 1. Extract the 15-character coordinate base (e.g., '369356N1218642W')
        df['base_location_id'] = df['site_code'].astype(str).str[:15]
        
        # 2. Add the node count DIRECTLY to the dataframe so it gets downloaded
        df['node_count'] = df.groupby('base_location_id')['site_code'].transform('count')
        
        # Optional: Compress it to a tiny 8-bit integer to keep RAM usage incredibly low
        df['node_count'] = df['node_count'].fillna(1).astype('int8')
        
        # 3. Label them based on the count
        df['computed_well_structure'] = 'Single-Node Well'
        df.loc[df['node_count'] > 1, 'computed_well_structure'] = 'Multi-Node Well'
        
        # 4. Clean up the temporary column to save memory
        df = df.drop(columns=['base_location_id'])
        # ====================================================
        
        # COMPRESS DATAFRAME TEXT: Converts heavy string objects to lightweight categories
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].astype('category')
        return df

    except Exception as e:
        print(f"Database extraction error during startup: {e}")
        return pd.DataFrame(columns=[
            'site_code', 'well_name', 'latitude', 'longitude', 
            'county_name', 'basin_name', 'well_use', 'well_type', 
            'monitoring_program', 'MONITORING_NETWORK_TYPE'
        ])

# Initialize cache on server boot
print("Booting map cache... fetching spatial data from CKAN.")
df_master_cache = load_master_network_cache()
print(f"Map cache initialized with {len(df_master_cache)} records.")

# Generate Dropdown Options Safely
COUNTY_OPTIONS = [{"label": str(c), "value": str(c)} for c in sorted([x for x in df_master_cache["county_name"].unique() if pd.notna(x)])]
BASIN_OPTIONS = [{"label": str(b), "value": str(b)} for b in sorted([x for x in df_master_cache["basin_name"].unique() if pd.notna(x)])]
USE_OPTIONS = [{"label": str(u), "value": str(u)} for u in sorted([x for x in df_master_cache["well_use"].unique() if pd.notna(x)])]
TYPE_OPTIONS = [{"label": str(t), "value": str(t)} for t in sorted([x for x in df_master_cache["well_type"].unique() if pd.notna(x)])]
PROGRAM_OPTIONS = [{"label": str(p), "value": str(p)} for p in sorted([x for x in df_master_cache["monitoring_program"].unique() if pd.notna(x)])]


# ==========================================
# 2. PAGE LAYOUT
# ==========================================
# Create a pointer to the 'window.customMap' object we built in the JS file
ns = Namespace("customMap", "default")
layout = dbc.Container([
    dbc.Row([
        # --- LEFT SIDEBAR: FILTERS ---
        dbc.Col([
            html.H4("CA WELL NETWORKS", className="bg-primary text-white p-2 mb-3 mt-2 rounded"),
            html.P("Filter telemetry configurations and network structures across California basins.", className="text-muted small"),
            
            html.Label("County Bound", className="fw-bold small"),
            dcc.Dropdown(id="map-filter-county", options=COUNTY_OPTIONS, multi=True, placeholder="All California Counties", className="mb-3"),
            
            html.Label("Bulletin 118 Basin", className="fw-bold small"),
            dcc.Dropdown(id="map-filter-basin", options=BASIN_OPTIONS, multi=True, placeholder="All Hydrogeologic Basins", className="mb-3"),
            
            html.Label("Well Primary Use", className="fw-bold small"),
            dcc.Dropdown(id="map-filter-use", options=USE_OPTIONS, multi=True, placeholder="All Use Classifications", className="mb-3"),
            
            html.Label("Well Structure Type", className="fw-bold small"),
            dcc.Dropdown(id="map-filter-type", options=TYPE_OPTIONS, multi=True, placeholder="All Structural Types", className="mb-3"),
            
            html.Label("Monitoring Program Source", className="fw-bold small"),
            dcc.Dropdown(id="map-filter-program", options=PROGRAM_OPTIONS, multi=True, placeholder="All Reporting Programs", className="mb-4"),
            
            html.Label("SGMA Network Protocol", className="fw-bold small border-bottom w-100 pb-1"),
            dbc.Checklist(
                id="map-filter-sgma",
                options=[
                    {"label": " SGMA Representative Well", "value": "SGMA Representative"},
                    {"label": " Non-Representative Well", "value": "Non-Representative"},
                ],
                value=["SGMA Representative", "Non-Representative"],
                className="mb-4 small"
            ),
            
            # Metrics Output Box
            html.Div(id="usgs-dynamic-summary-box", className="bg-light border p-3 rounded mt-auto"),

            # --- DOWNLOAD BUTTON (Global Filtered Data) ---
            dbc.Button("⬇ Download Filtered Stations (CSV)", id="btn-download-map", color="success", className="mt-3 w-100 fw-bold"),
            dcc.Download(id="download-map-csv"),
            
            # --- AOI DEEP DATA DOWNLOAD UI ---
            dbc.Button("💧 Download Measurements for a custom Area of Interest (AOI) (CSV)", id="btn-download-aoi", color="info", className="mt-2 w-100 fw-bold"),
            # html.Div(id="aoi-download-alert", className="mt-2"), # Shows warnings if area is too big
            # This alert is now invisible; we use it strictly as a hidden signal to tell Javascript that Python finished
            # html.Div(id="aoi-download-alert", style={"display": "none"}),
            dcc.Download(id="download-aoi-csv"),
            # Native Dash Timer Components (Invisible)
            dcc.Interval(id="dl-interval", interval=1000, n_intervals=0, disabled=True),
            # THE DOWNLOAD UX MODAL
            dbc.Modal(
                [
                    dbc.ModalHeader(dbc.ModalTitle("Extracting Deep Time-Series Data"), close_button=False),
                    dbc.ModalBody(
                        html.Div([
                            html.H5(id="dl-modal-text", children="Querying California CKAN API...", className="fw-bold text-center mt-2"),
                            html.P(id="dl-modal-subtext", children="Compiling massive datasets. This may take 1-2 minutes.", className="text-muted small text-center"),
                            html.Div(dbc.Spinner(color="info", size="lg"), id="dl-spinner-container", className="mt-4 mb-4"),
                            html.H2(id="dl-timer-display", children="00:00", className="text-secondary font-monospace")
                        ], className="d-flex flex-column align-items-center justify-content-center py-4")
                    ),
                    dbc.ModalFooter(
                        dbc.Button("Close", id="btn-close-dl-modal", color="success", className="d-none") 
                    )
                ],
                id="dl-modal",
                is_open=False,
                backdrop="static", # Prevents clicking outside to close
                keyboard=False,
                centered=True
            )
        ], md=3, className="d-flex flex-column border-end shadow-sm", style={"height": "100vh", "overflowY": "auto"}),
        
        # --- RIGHT MAIN SECTION: LEAFLET CANVAS ---
        dbc.Col([
            dl.Map(
                id="leaflet-gis-map",
                center=[36.7783, -119.4179], 
                zoom=6,
                children=[
                    dl.TileLayer(id="base-tile-layer"), 
                    dl.GeoJSON(
                        id="leaflet-markers-layer",
                        # Calls window.customMap.drawDot
                        options=dict(pointToLayer=ns("drawDot"))
                        # cluster=True,  # Activates Leaflet's high-performance clustering
                        # zoomToBoundsOnClick=True,
                        # superClusterOptions={"radius": 40, "maxClusterRadius": 50}
                    )
                ],
                style={'width': '100%', 'height': '100vh'}
            )
        ], md=9, className="p-0 position-relative")
    ], className="g-0")
], fluid=True, className="p-0")


# ==========================================
# 3. INTERACTIVITY CALLBACKS
# ==========================================
@callback(
    Output("leaflet-markers-layer", "data"), 
    Output("usgs-dynamic-summary-box", "children"),
    Input("leaflet-gis-map", "bounds"),
    Input("map-filter-county", "value"),
    Input("map-filter-basin", "value"),
    Input("map-filter-use", "value"),
    Input("map-filter-type", "value"),
    Input("map-filter-program", "value"),
    Input("map-filter-sgma", "value")
)

def execute_network_spatial_filter(map_bounds, counties, basins, uses, types, programs, sgma_types):
    working_df = df_master_cache.copy()
    
    # 1. Apply Categorical Filters
    if counties:
        working_df = working_df[working_df['county_name'].isin(counties)]
    if basins:
        working_df = working_df[working_df['basin_name'].isin(basins)]
    if uses:
        working_df = working_df[working_df['well_use'].isin(uses)]
    if types:
        working_df = working_df[working_df['well_type'].isin(types)]
    if programs:
        working_df = working_df[working_df['monitoring_program'].isin(programs)]
    if sgma_types:
        working_df = working_df[working_df['MONITORING_NETWORK_TYPE'].isin(sgma_types)]
    else:
        working_df = working_df.iloc[0:0]

    total_filtered_attributes = len(working_df)

    # 2. Apply Spatial Bounding Box Filter
    if map_bounds:
        south, west = map_bounds[0][0], map_bounds[0][1]
        north, east = map_bounds[1][0], map_bounds[1][1]
        spatial_df = working_df[
            (working_df['latitude'] >= south) & (working_df['latitude'] <= north) &
            (working_df['longitude'] >= west) & (working_df['longitude'] <= east)
        ]
    else:
        spatial_df = working_df

    total_visible_sites = len(spatial_df)
    representative_count = len(spatial_df[spatial_df['MONITORING_NETWORK_TYPE'] == 'SGMA Representative'])


    # 3. Compile Pandas Data into Native GeoJSON Dictionary (MEMORY OPTIMIZED)
    features = []
    
    for row in spatial_df.itertuples(index=False):
        # Safely handle potential empty text fields
        well_name_str = str(row.well_name) if pd.notna(row.well_name) else 'Unknown Well'
        sgma_str = str(row.MONITORING_NETWORK_TYPE) if pd.notna(row.MONITORING_NETWORK_TYPE) else 'Non-Representative'
        
        # We just pass the raw data, NO HTML strings!
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row.longitude, row.latitude] 
            },
            "properties": {
                "tooltip": f"{row.site_code}| {well_name_str}",
                "site_code": row.site_code,
                "well_name": well_name_str,
                "basin_name": str(row.basin_name) if pd.notna(row.basin_name) else 'N/A',
                "county_name": str(row.county_name) if pd.notna(row.county_name) else 'N/A',
                "sgma_status": sgma_str
            }
        })

    geojson_payload = {
        "type": "FeatureCollection",
        "features": features
    }

    # 4. Format USGS-Style Metrics Display
    summary_metrics_ui = html.Div([
        html.Div([
            html.Span("SITES IN VIEW: ", className="fw-bold text-muted"), 
            html.Strong(f"{total_visible_sites:,}", className="text-primary fs-5")
        ], className="mb-1"),
        html.Div([
            html.Span("SGMA REP TYPE: ", className="fw-bold text-muted"), 
            html.Strong(f"{representative_count:,}", className="text-success fs-5")
        ], className="mb-2"),
        html.Hr(className="my-2 border-secondary"),
        html.Div([
            html.Span("GLOBAL MATCH: "), html.Span(f"{total_filtered_attributes:,} total records")
        ], className="small text-muted")
    ])

    return geojson_payload, summary_metrics_ui


# ==========================================
# 3. INTERACTIVITY CALLBACKS
# ==========================================
@callback(
    Output("download-map-csv", "data"),
    Input("btn-download-map", "n_clicks"),
    # Pull the exact same filter values currently active on the page
    State("map-filter-county", "value"),
    State("map-filter-basin", "value"),
    State("map-filter-use", "value"),
    State("map-filter-type", "value"),
    State("map-filter-program", "value"),
    State("map-filter-sgma", "value"),
    prevent_initial_call=True
)
def download_filtered_stations(n_clicks, counties, basins, uses, types, programs, sgma_types):
    """
    Exports the currently filtered directory of groundwater monitoring stations to CSV.
    
    This callback intercepts the active state of the UI filters, applies them 
    against the globally cached master station dataframe, and dynamically 
    generates a downloadable CSV file. It strictly exports metadata and 
    spatial coordinates (the "directory"), intentionally excluding heavy 
    time-series data to ensure low latency and memory efficiency.
    """
    
    # SAFETY CATCH: If the button hasn't been clicked, do absolutely nothing
    if not n_clicks:
        return no_update

    # Clone the master cache to prevent mutating the global application state
    working_df = df_master_cache.copy()
    
    # Apply spatial and categorical filters to find out what is on the screen
    if counties: working_df = working_df[working_df['county_name'].isin(counties)]
    if basins: working_df = working_df[working_df['basin_name'].isin(basins)]
    if uses: working_df = working_df[working_df['well_use'].isin(uses)]
    if types: working_df = working_df[working_df['well_type'].isin(types)]
    if programs: working_df = working_df[working_df['monitoring_program'].isin(programs)]
    if sgma_types: working_df = working_df[working_df['MONITORING_NETWORK_TYPE'].isin(sgma_types)]
    
    # Send the filtered dataframe directly to the user's browser as a CSV!
    return dcc.send_data_frame(working_df.to_csv, "filtered_california_stations.csv", index=False)    

# ==========================================
# 3. INTERACTIVITY CALLBACKS
# ==========================================
'''
@callback(
    Output("download-aoi-csv", "data"),
    Output("aoi-download-alert", "children"),
    Input("btn-download-aoi", "n_clicks"),
    State("leaflet-gis-map", "bounds"),
    State("map-filter-county", "value"),
    State("map-filter-basin", "value"),
    State("map-filter-use", "value"),
    State("map-filter-type", "value"),
    State("map-filter-program", "value"),
    State("map-filter-sgma", "value"),
    prevent_initial_call=True
)
def export_aoi_measurements(n_clicks, map_bounds, counties, basins, uses, types, programs, sgma_types):
    """
    Extracts deep time-series measurement data for a targeted Area of Interest (AOI).
    
    Evaluates the spatial bounding box of the active map view alongside active 
    categorical filters to isolate a specific subset of wells. To prevent 
    out-of-memory (OOM) failures during dynamic data extraction, this function 
    enforces a strict safety limit (MAX_WELL_LIMIT). Valid requests compile 
    the targeted site codes into an optimized SQL 'IN' clause for the API.
    """
    # SAFETY CATCH: If the button hasn't been clicked, do absolutely nothing
    if not n_clicks:
        return dash.no_update, dash.no_update
        # We can't actually 'stream' an alert to the screen halfway through a callback, 
        # but having the dcc.Loading spinner combined with the exact language on your button 
        # sets the right expectation.
    
    # 1. Clone the master cache to prevent mutating the global application state
    working_df = df_master_cache.copy()
    
    # 2. Apply spatial and categorical filters to find out what is on the screen
    if counties: working_df = working_df[working_df['county_name'].isin(counties)]
    if basins: working_df = working_df[working_df['basin_name'].isin(basins)]
    if uses: working_df = working_df[working_df['well_use'].isin(uses)]
    if types: working_df = working_df[working_df['well_type'].isin(types)]
    if programs: working_df = working_df[working_df['monitoring_program'].isin(programs)]
    if sgma_types: working_df = working_df[working_df['MONITORING_NETWORK_TYPE'].isin(sgma_types)]
    
    # Apply spatial bounding box filter
    if map_bounds:
        south, west = map_bounds[0][0], map_bounds[0][1]
        north, east = map_bounds[1][0], map_bounds[1][1]
        spatial_df = working_df[
            (working_df['latitude'] >= south) & (working_df['latitude'] <= north) &
            (working_df['longitude'] >= west) & (working_df['longitude'] <= east)
        ]
    else:
        spatial_df = working_df

    # 3. THE KILL SWITCH: Hardware protection constraint
    # Prevents users from querying massive datasets that would exceed the server's RAM limit.
    MAX_WELL_LIMIT = 200 # You can adjust this to 75 or 100 after testing RAM usage
    total_wells = len(spatial_df)
    
    # Return early if no wells are in the view
    if total_wells == 0:
        return dash.no_update, dbc.Alert("No wells in current view.", color="warning", duration=4000)
        
    if total_wells > MAX_WELL_LIMIT:
        warning_msg = f"Area too large! You selected {total_wells} wells. Please zoom in or filter to {MAX_WELL_LIMIT} or fewer wells to extract deep time-series data."
        return dash.no_update, dbc.Alert(warning_msg, color="danger", duration=6000)

    # 4. Extract the isolated Site Codes
    target_site_codes = spatial_df['site_code'].tolist()
    
    # Drop the chunk size to 15. This makes more API calls, but keeps RAM perfectly flat.
    CHUNK_SIZE = 15 
    
    # Create a temporary file on the Render server's hard drive
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv')
    temp_filepath = temp_file.name
    temp_file.close()

    first_chunk = True # We use this to decide when to write the CSV headers

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Loop through the target codes in small batches
        for i in range(0, len(target_site_codes), CHUNK_SIZE):
            chunk = target_site_codes[i:i + CHUNK_SIZE]
            
            formatted_codes = ", ".join([f"'{code}'" for code in chunk])
            sql_query = f'SELECT * FROM "{RESOURCES["measurements"]}" WHERE "site_code" IN ({formatted_codes})'
            
            # Fetch just this small chunk
            chunk_records = loop.run_until_complete(execute_sql_paginated(sql_query))
            
            if chunk_records:
                # Convert only this tiny chunk to a dataframe
                df_chunk = pd.DataFrame(chunk_records)
                
                # Clean up State API junk columns
                junk_columns = ['_full_text', 'full_text', '_id']
                existing_junk = [col for col in junk_columns if col in df_chunk.columns]
                if existing_junk:
                    df_chunk = df_chunk.drop(columns=existing_junk)
                
                # WRITE DIRECTLY TO THE HARD DRIVE (mode='a' means append)
                df_chunk.to_csv(temp_filepath, mode='a', header=first_chunk, index=False)
                first_chunk = False # Never write headers again for this file
                
            # AGGRESSIVELY DELETE VARIABLES TO FREE RAM INSTANTLY
            del chunk_records
            if 'df_chunk' in locals():
                del df_chunk
            gc.collect()

        # If the file is still empty, no data was found
        if first_chunk:
             os.remove(temp_filepath) # Clean up the hard drive
             return dash.no_update, dbc.Alert("No measurement data found for these specific wells.", color="warning", duration=4000)
             
        # Create a memory-safe generator to stream the file to the user's browser, then delete the temp file
        def stream_and_delete(buffer):
            with open(temp_filepath, "rb") as f:
                # yield from f
                # Safely stream it chunk-by-chunk into Dash's browser buffer
                shutil.copyfileobj(f, buffer)
            
            # Clean up: Delete the temporary file from the server
            os.remove(temp_filepath)

        # Send the file to the user!
        success_msg = f"Successfully downloaded deep data for the selected area."
        return dcc.send_bytes(stream_and_delete, "AOI_Groundwater_Measurements.csv"), dbc.Alert(success_msg, color="success", duration=5000)

    except Exception as e:
        print(f"AOI Export Error: {e}")
        # Clean up the temp file if the API crashes
        if os.path.exists(temp_filepath):
            os.remove(temp_filepath)
        return dash.no_update, dbc.Alert("Database timeout or error. Try selecting a smaller area.", color="danger", duration=4000)

'''

@callback(
    Output("dl-modal", "is_open"),
    Output("dl-interval", "disabled"),
    Output("dl-interval", "n_intervals"), 
    Output("dl-modal-text", "children"),
    Output("dl-modal-subtext", "children"),
    Output("dl-spinner-container", "style"),
    Output("btn-close-dl-modal", "className"),
    Output("dl-timer-display", "className"),
    Input("btn-download-aoi", "n_clicks"),
    Input("btn-close-dl-modal", "n_clicks"),
    prevent_initial_call=True
)
def handle_modal_open_close(open_clicks, close_clicks):
    trigger = dash.ctx.triggered_id
    
    if trigger == "btn-download-aoi":
        # OPEN MODAL & RESET UI
        return (
            True, False, 0, 
            "Querying California CKAN API...", 
            "Compiling massive datasets. This may take 1-2 minutes.", 
            {"display": "block"}, "d-none", "text-secondary font-monospace"
        )
    elif trigger == "btn-close-dl-modal":
        # CLOSE MODAL & STOP TIMER
        return (
            False, True, 0, 
            dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
        )
    
    return [dash.no_update] * 8


@callback(
    Output("download-aoi-csv", "data"),
    Output("dl-modal-text", "children", allow_duplicate=True),
    Output("dl-modal-subtext", "children", allow_duplicate=True),
    Output("dl-spinner-container", "style", allow_duplicate=True),
    Output("btn-close-dl-modal", "className", allow_duplicate=True),
    Output("dl-timer-display", "className", allow_duplicate=True),
    Output("dl-interval", "disabled", allow_duplicate=True),
    Input("dl-modal", "is_open"), # <-- THE CHAIN: This only fires when the modal physically opens
    State("leaflet-gis-map", "bounds"),
    State("map-filter-county", "value"),
    State("map-filter-basin", "value"),
    State("map-filter-use", "value"),
    State("map-filter-type", "value"),
    State("map-filter-program", "value"),
    State("map-filter-sgma", "value"),
    prevent_initial_call=True,
    background=True,
    manager=background_callback_manager
)
def run_heavy_download(is_open, map_bounds, counties, basins, uses, types, programs, sgma_types):
    if not is_open:
        return [dash.no_update] * 7
        
    # 1. Re-apply Filters
    working_df = df_master_cache.copy()
    if counties: working_df = working_df[working_df['county_name'].isin(counties)]
    if basins: working_df = working_df[working_df['basin_name'].isin(basins)]
    if uses: working_df = working_df[working_df['well_use'].isin(uses)]
    if types: working_df = working_df[working_df['well_type'].isin(types)]
    if programs: working_df = working_df[working_df['monitoring_program'].isin(programs)]
    if sgma_types: working_df = working_df[working_df['MONITORING_NETWORK_TYPE'].isin(sgma_types)]
    
    if map_bounds:
        south, west = map_bounds[0][0], map_bounds[0][1]
        north, east = map_bounds[1][0], map_bounds[1][1]
        spatial_df = working_df[
            (working_df['latitude'] >= south) & (working_df['latitude'] <= north) &
            (working_df['longitude'] >= west) & (working_df['longitude'] <= east)
        ]
    else:
        spatial_df = working_df

    # 2. Check Limits
    MAX_WELL_LIMIT = 200 
    total_wells = len(spatial_df)
    
    if total_wells == 0 or total_wells > MAX_WELL_LIMIT:
        error_sub = "No wells in view." if total_wells == 0 else f"Selected {total_wells} wells. Limit is {MAX_WELL_LIMIT}."
        return (
             dash.no_update, "⚠️ Download Failed", error_sub, {"display": "none"}, 
             "btn btn-danger text-white fw-bold", "text-danger fw-bold font-monospace mt-2", True
        )

    # 3. PURE PYTHON NATIVE CSV SPOOLING (Zero-Pandas)
    
    target_site_codes = spatial_df['site_code'].tolist()
    CHUNK_SIZE = 15 
    
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.csv', mode='w', newline='', encoding='utf-8')
    temp_filepath = temp_file.name
    
    # Bypass RAM entirely by streaming text directly to the hard drive
    csv_writer = csv.writer(temp_file)
    headers_written = False

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        for i in range(0, len(target_site_codes), CHUNK_SIZE):
            chunk = target_site_codes[i:i + CHUNK_SIZE]
            formatted_codes = ", ".join([f"'{code}'" for code in chunk])
            sql_query = f'SELECT * FROM "{RESOURCES["measurements"]}" WHERE "site_code" IN ({formatted_codes})'
            
            chunk_records = loop.run_until_complete(execute_sql_paginated(sql_query))
            
            if chunk_records:
                # Manually strip CKAN system keys
                junk_keys = ['_full_text', 'full_text', '_id']
                for record in chunk_records:
                    for key in junk_keys:
                        record.pop(key, None)
                
                # Write headers only once
                if not headers_written:
                    headers = list(chunk_records[0].keys())
                    csv_writer.writerow(headers)
                    headers_written = True
                
                # Write rows directly to disk
                for row in chunk_records:
                    csv_writer.writerow(row.values())
                    
            del chunk_records
            gc.collect()

        # Unlock the file from the OS so Dash can read it
        temp_file.close()

        if not headers_written:
             if os.path.exists(temp_filepath): os.remove(temp_filepath)
             return (dash.no_update, "⚠️ Error", "No measurements found.", {"display": "none"}, "btn btn-danger text-white fw-bold", "text-danger fw-bold font-monospace mt-2", True)
             
        def stream_and_delete(buffer):
            with open(temp_filepath, "rb") as f:
                shutil.copyfileobj(f, buffer)
            os.remove(temp_filepath)

        # 4. Success UI Update!
        return (
            dcc.send_bytes(stream_and_delete, "AOI_Groundwater_Measurements.csv"),
            "✅ Download Complete!",
            "Your time-series data has been successfully fetched and is in your Downloads folder.",
            {"display": "none"}, # Hide spinner
            "btn btn-success text-white fw-bold", # Show close button
            "text-success fw-bold font-monospace mt-2", # Green timer text
            True # Disable timer
        )

    except Exception as e:
        print(f"AOI Export Error: {e}")
        temp_file.close()
        if os.path.exists(temp_filepath): os.remove(temp_filepath)
        return (dash.no_update, "⚠️ Database Error", "Timeout or connection error.", {"display": "none"}, "btn btn-danger text-white fw-bold", "text-danger fw-bold font-monospace mt-2", True)

# Uses the browser to count seconds natively so it doesn't wait on the blocked Python server
clientside_callback(
    """
    function(n_intervals) {
        if (!n_intervals) { return "00:00"; }
        const mins = Math.floor(n_intervals / 60).toString().padStart(2, '0');
        const secs = (n_intervals % 60).toString().padStart(2, '0');
        return mins + ":" + secs;
    }
    """,
    Output("dl-timer-display", "children"),
    Input("dl-interval", "n_intervals")
)

