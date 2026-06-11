import sys
import os
import asyncio
import pandas as pd
import dash
from dash import dcc, html, Input, Output, State
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

from components.hydrograph import generate_interactive_hydrograph_logic
from components.well_profile import create_well_profile_figure, create_construction_table
from components.accordions import create_dashboard_accordions

app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])
server = app.server  # <--- Add this exact line! Render will look for this 'server' variable.

# ---------------------------------------------------------
# 2. Layout Generation (Now with Dropdown & Loading Spinner)
# ---------------------------------------------------------
def serve_layout(dropdown_options):
    """Assembles the UI grid. Graphs start empty and wait for the Master Callback."""
    return dbc.Container([
        # Header & Control Row
        dbc.Row([
            dbc.Col(html.H2("Groundwater Monitoring Dashboard", className="mt-4 mb-2 text-primary"), width=12),
            dbc.Col([
                html.Label("Search & Select a Well:", className="fw-bold text-muted mb-1"),
                dcc.Dropdown(
                    id='well-selector',
                    options=dropdown_options,
                    value="369604N1219650W003", # Default starting well
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

    # 3. Construct all UI components
    hydro_fig = await generate_interactive_hydrograph_logic(
        site_code=site_code,
        get_measurements_func=get_measurements,
        get_records_func=get_records_by_attribute,
        get_wy_func=get_water_years
    )
    well_fig = create_well_profile_figure(site_code, screens_df, gse_val)
    const_table = create_construction_table(screens_df) 
    accordions = create_dashboard_accordions(site_code, station_records, gsp_records, measurements_records, perf_records)
    
    return hydro_fig, well_fig, const_table, accordions


# ---------------------------------------------------------
# 4. Interactive Callbacks
# ---------------------------------------------------------

@app.callback(
    [
        Output('hydrograph-chart', 'figure'),
        Output('well-profile-graph', 'figure'),
        Output('construction-table-container', 'children'),
        Output('accordions-container', 'children')
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
    hydro_fig, well_fig, const_table, accordions = loop.run_until_complete(build_dashboard_figures(selected_site_code))
    loop.close()

    return hydro_fig, well_fig, const_table, accordions


@app.callback(
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
    return options

def open_browser():
    webbrowser.open_new("http://127.0.0.1:8050")

if __name__ == '__main__':
    # 1. Quickly grab the list of wells for the menu
    menu_options = asyncio.run(fetch_dropdown_wells())
    
    # Ensure our default well is in the list just in case it wasn't in the top 500
    if not any(opt['value'] == "369604N1219650W003" for opt in menu_options):
        menu_options.insert(0, {"label": "Pleasure PT. Deep (369604N1219650W003)", "value": "369604N1219650W003"})

    # 2. Render the layout (It will load empty, and the callback will instantly trigger to fill it)
    app.layout = serve_layout(menu_options)
    
    # Only open the browser in the main worker process, avoiding the double-tab bug
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        Timer(1, open_browser).start()

    print("Dashboard architecture fully initialized. Launching server at http://127.0.0.1:8050")
    app.run(debug=True, port=8050)