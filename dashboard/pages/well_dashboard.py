import sys
import os
import asyncio
import pandas as pd
import dash
from dash import dcc, html, Input, Output, State, callback
import dash_bootstrap_components as dbc
import webbrowser
from threading import Timer

# ---------------------------------------------------------
# 1. Directory Routing & Imports
# ---------------------------------------------------------
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from mcp_api.server import (
    get_measurements, 
    get_records_by_attribute, 
    get_water_years, 
    get_station_info,
    execute_sql_paginated, 
    RESOURCES              
)

from dashboard.components.hydrograph import generate_interactive_hydrograph_logic
from dashboard.components.well_profile import create_well_profile_figure, create_construction_table
from dashboard.components.accordions import create_dashboard_accordions

# --- MULTI-PAGE APP REGISTRATION ---
# This tells Dash exactly where this page lives and allows it to accept ?id= query strings
dash.register_page(__name__, path='/well-dashboard')
# app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
# server = app.server  # <--- Add this exact line! Render will look for this 'server' variable.

# ---------------------------------------------------------
# 2. Layout Generation (Now with Dropdown & Loading Spinner)
# ---------------------------------------------------------
def serve_layout(dropdown_options, starting_well):
    """Assembles the UI grid. Graphs start empty and wait for the Master Callback."""
    return dbc.Container([
        # Header & Control Row
        dbc.Row([
            dbc.Col([
                html.H2("Groundwater Monitoring Dashboard", className="mt-4 mb-2 text-primary d-inline-block"),
                html.Span(id="sgma-status-badge", className="ms-3 mb-2 align-middle") # <-- Added Badge Placeholder
            ], width=12),
            dbc.Col([
                html.Label("Search & Select a Well:", className="fw-bold text-muted mb-1"),
                dcc.Dropdown(
                    id='well-selector',
                    options=dropdown_options,
                    value=starting_well, # # dynamically set based on the URL ID!
                    clearable=False,
                    className="shadow-sm mb-4"
                )
            ], md=6, lg=4)
        ]),
        
        # We wrap the entire visual dashboard in a Loading component 
        # so a spinner appears while the API is fetching the new well's data.
        # REMOVED the giant dcc.Loading wrapper and the dashboard-content Div
        
        dbc.Row([
            # Left: Hydrograph (Now holds the Loading Spinner exclusively)
            dbc.Col([
                dbc.Card(dbc.CardBody(
                    dcc.Loading(
                        type="circle",
                        color="#2563EB",
                        children=dcc.Graph(id='hydrograph-chart', style={'height': '650px'}, hoverData=None)
                    )
                ), className="shadow-sm")
            ], md=7),
            
            # Right: Well Sketch & Construction Table (Freed from the spinner trap)
            dbc.Col([
                dbc.Card(dbc.CardBody(
                    dbc.Row([
                        dbc.Col(
                            dcc.Graph(id='well-profile-graph', style={'height': '650px'}, 
                                      config={'staticPlot': False}, animation_options={'transition': {'duration': 0}}),
                            width=7, className="pe-0"
                        ),
                        dbc.Col(
                            html.Div(id='construction-table-container'), 
                            width=5, className="ps-0 pt-5" 
                        )
                    ])
                ), className="shadow-sm")
            ], md=5) 
        ]),
        
        # Bottom: Expandable Accordions
        dbc.Row([
            dbc.Col(html.Div(id='accordions-container'), width=12)
        ])
        
    ], fluid=True, className="bg-light pb-5", style={"minHeight": "100vh"})


# ---------------------------------------------------------
# 3. The Master Data Fetcher (Runs on every dropdown change)
# ---------------------------------------------------------
async def build_dashboard_figures(site_code: str):
    """Executes all API calls and builds all UI components for the selected well."""
    # 1. Fire parallel network requests
    station_task = get_station_info(site_code)
    gsp_task = get_records_by_attribute("gsp_monitoring", "SITE_CODE", site_code)
    msmt_task = get_measurements(site_code)
    
    # 2. Fetch all sibling nodes for the borehole using the 15-char prefix
    prefix = site_code[:15]
    perf_sql = f'SELECT * FROM "{RESOURCES["perforations"]}" WHERE "site_code" LIKE \'{prefix}%\''
    perf_task = execute_sql_paginated(perf_sql)
    
    station_records, gsp_records, measurements_records, perf_records = await asyncio.gather(
        station_task, gsp_task, msmt_task, perf_task
    )

    gse_val = "N/A"
    if station_records:
        try:
            gse_val = float(station_records[0].get('gse'))
        except (TypeError, ValueError):
            pass

    screens_df = pd.DataFrame()
    if perf_records:
        screens_df = pd.DataFrame(perf_records)
        screens_df.rename(columns={'top_prf_int': 'TOP_PRF', 'bot_prf_int': 'BOT_PRF', 'site_code': 'SITE_CODE'}, inplace=True)
        screens_df['TOP_PRF'] = pd.to_numeric(screens_df['TOP_PRF'], errors='coerce')
        screens_df['BOT_PRF'] = pd.to_numeric(screens_df['BOT_PRF'], errors='coerce')
        screens_df.dropna(subset=['TOP_PRF', 'BOT_PRF'], inplace=True)

    # --- NEW: Evaluate SGMA Status ---
    is_representative = False
    if gsp_records:
        for r in gsp_records:
            # Safely check for the network type string
            net_type = str(r.get("MONITORING_NETWORK_TYPE", r.get("monitoring_network_type", "")))
            if net_type.strip() == "SGMA Representative":
                is_representative = True
                break

    # Create a dynamic Bootstrap badge
    if is_representative:
        status_badge = dbc.Badge("SGMA Representative", color="success", className="fs-6 shadow-sm")
    else:
        status_badge = dbc.Badge("Non-Representative", color="secondary", className="fs-6 shadow-sm")

    # 3. Construct all UI components
    hydro_fig = await generate_interactive_hydrograph_logic(
        site_code=site_code,
        get_measurements_func=get_measurements,
        get_records_func=get_records_by_attribute,
        get_wy_func=get_water_years
    )
    well_fig = create_well_profile_figure(site_code, screens_df, gse_val)
    const_table = create_construction_table(screens_df) 
    accordions = create_dashboard_accordions(site_code, station_records, gsp_records, measurements_records, perf_records, is_representative)
    
    return hydro_fig, well_fig, const_table, accordions, status_badge


# ---------------------------------------------------------
# 4. Interactive Callbacks
# ---------------------------------------------------------
# Changed to global @callback
@callback(
    [
        Output('hydrograph-chart', 'figure'),
        Output('well-profile-graph', 'figure'),
        Output('construction-table-container', 'children'),
        Output('accordions-container', 'children'),
        Output('sgma-status-badge', 'children') # <-- NEW OUTPUT
    ],
    Input('well-selector', 'value')
)
def update_entire_dashboard(selected_site_code):
    """Listens to the Dropdown. When a new well is picked, it redraws everything."""
    if not selected_site_code:
        return dash.no_update

    # Because Dash runs synchronously, but our fetchers are async, 
    # we create a temporary event loop just to run the downloads.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    hydro_fig, well_fig, const_table, accordions, status_badge = loop.run_until_complete(build_dashboard_figures(selected_site_code))
    loop.close()

    return hydro_fig, well_fig, const_table, accordions, status_badge


@callback(
    Output('well-profile-graph', 'figure', allow_duplicate=True),
    Input('hydrograph-chart', 'hoverData'),
    State('well-profile-graph', 'figure'),
    prevent_initial_call=True
)
def sync_water_level(hover_data, well_fig):
    """Listens to the hydrograph hover events and updates the well profile water level."""
    if not hover_data or not well_fig: 
        return dash.no_update
        
    try:
        point_data = hover_data['points'][0]
        if 'y' in point_data and isinstance(point_data['y'], (int, float)):
            current_elevation = point_data['y']
            for trace in well_fig['data']:
                if trace.get('name') == 'DynamicWaterLevel':
                    trace['y'] = [current_elevation, current_elevation, current_elevation]
                    break
        return well_fig
    except Exception:
        return dash.no_update


# ---------------------------------------------------------
# 5. Bootstrapper
# ---------------------------------------------------------
async def fetch_dropdown_wells():
    """Fetches a list of monitored wells to populate the search bar on startup."""
    print("Fetching active monitoring wells for the dropdown menu...")
    # We query the GSP monitoring table here to get a clean list of active regulatory wells
    sql = f'SELECT "SITE_CODE", "WELL_NAME" FROM "{RESOURCES["gsp_monitoring"]}"'
    records = await execute_sql_paginated(sql)
    
    options = []
    for r in records:
        name = str(r.get("WELL_NAME", r["SITE_CODE"]))
        if name.strip().lower() in ["none", "nan", ""]:
            name = r["SITE_CODE"]
        options.append({"label": f"{name} ({r['SITE_CODE']})", "value": r['SITE_CODE']})

    # --- Sort by the site_code (which is stored in the 'value' key) ---
    # California well site codes are constructed using latitude and longitude coordinates
    # sorting alphabetically by the site_code naturally groups geographically clustered wells right next to each other in the dropdown list
    options = sorted(options, key=lambda k: k['value'])
    return options



# Define a wrapper function for the layout that can execute globally
# In an MPA, the layout MUST be a function if it accepts URL parameters
def layout(id=None, name=None, **kwargs):
    try:
        # Create a new loop so we can fetch options synchronously during page load
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        menu_options = loop.run_until_complete(fetch_dropdown_wells())
        loop.close()
    except Exception:
        menu_options = []
    
    # 1. Grab the ID passed from the Map URL, or default to a safe fallback
    starting_well = id if id else "369604N1219650W003"
    # Grab the specific Name passed from the Map URL (or default to Unknown)
    display_name = name if name else "Unknown Well"

    # 2. If the map passed a valid ID that isn't in our dropdown list, force it in
    if starting_well and not any(opt['value'] == starting_well for opt in menu_options):
        #menu_options.insert(0, {"label": f"Selected Map Well ({starting_well})", "value": starting_well})
        menu_options.insert(0, {"label": f"{display_name} ({starting_well})", "value": starting_well})

    # 3. Serve the layout, passing the specific well from the map to trigger the callback
    return serve_layout(menu_options, starting_well)
