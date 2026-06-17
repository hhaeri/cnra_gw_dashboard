import dash
from dash import dcc, html, Input, Output, callback
import dash_bootstrap_components as dbc
import dash_leaflet as dl
import pandas as pd
import asyncio
import gc  # MUST IMPORT GARBAGE COLLECTOR
from dash_extensions.javascript import Namespace
import urllib.parse

# Import your server tools
from mcp_api.server import execute_sql_paginated, RESOURCES

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
            
            if 'MONITORING_NETWORK_TYPE' in df_gsp.columns:
                df = pd.merge(
                    df_stations, 
                    df_gsp[['site_code', 'MONITORING_NETWORK_TYPE']], 
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
            html.Div(id="usgs-dynamic-summary-box", className="bg-light border p-3 rounded mt-auto")
            
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

    # 3. Compile Pandas Data into Native GeoJSON Dictionary
    features = []
    for _, row in spatial_df.iterrows():
        # 1. Safely encode the name so spaces and special characters don't break the URL
        raw_name = str(row.get('well_name', 'Unknown Well'))
        safe_name = urllib.parse.quote(raw_name)

        popup_html = f"""
            <div style='font-family: sans-serif; min-width: 220px;'>
                <h6 style='margin: 0px 0px 4px 0px; font-weight: bold;'>{raw_name}</h6>
                <p style='margin: 0px; font-size: 11px; color: #555;'><b>Basin:</b> {row.get('basin_name', 'N/A')}</p>
                <p style='margin: 0px 0px 8px 0px; font-size: 11px; color: #555;'><b>County:</b> {row.get('county_name', 'N/A')}</p>
                
                <a href='/well-dashboard?id={row['site_code']}&name={safe_name}' 
                   target='_blank' rel='noopener noreferrer'
                   style='display: block; background-color: #2c3e50; color: white; padding: 6px; 
                          text-align: center; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold;'>
                   Open Hydrograph Analytics ↗
                </a>
            </div>
        """
        
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row['longitude'], row['latitude']] # Longitude strictly first
            },
            "properties": {
                "tooltip": f"Well ID: {row['site_code']}",
                "popup": popup_html
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