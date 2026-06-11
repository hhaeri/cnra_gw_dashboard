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
# Dynamically add the parent directory (mcp_groundwater) to Python's path
# This allows the dashboard to use the tools without moving them from the root
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

# Import your deterministic fetching logic directly from the server module
from mcp_api.server import (
    get_measurements, 
    get_records_by_attribute, 
    get_water_years, 
    get_station_info,
    get_perforation_data,
    execute_sql_paginated,
    RESOURCES
)

# Import the decoupled UI components
from components.hydrograph import generate_interactive_hydrograph_logic
from components.well_profile import create_well_profile_figure, create_construction_table
from components.accordions import create_dashboard_accordions

# Initialize the Dash app with a clean Bootstrap theme
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.FLATLY])

# ---------------------------------------------------------
# 2. Layout Generation
# ---------------------------------------------------------
def serve_layout(hydro_fig, well_fig, const_table, accordions):
    """Assembles the UI grid using Dash Bootstrap Components."""
    return dbc.Container([
        dbc.Row([
            dbc.Col(html.H2("Groundwater Monitoring Dashboard", className="mt-4 mb-4 text-primary"), width=12)
        ]),
        
        # Main Visuals Row: Hydrograph (Left) and Borehole Profile (Right)
        dbc.Row([
            dbc.Col([
                dbc.Card(dbc.CardBody(
                    dcc.Graph(id='hydrograph-chart', figure=hydro_fig, style={'height': '650px'}, hoverData=None)
                ), className="shadow-sm")
            ], md=7),
            dbc.Col([
                dbc.Card(dbc.CardBody(
                    dbc.Row([
                        dbc.Col(
                            dcc.Graph(id='well-profile-graph', figure=well_fig, style={'height': '650px'}, 
                                      config={'staticPlot': False}, animation_options={'transition': {'duration': 0}}),
                            width=7, className="pe-0"
                        ),
                        dbc.Col(
                            const_table, # Inject the side construction table right next to the sketch
                            width=5, className="ps-0 pt-5" 
                        )
                    ])
                ), className="shadow-sm")
            ], md=5) # Expanded to hold the sketch + table
        ]),
        
        # Details Row: The expandable data tables
        dbc.Row([
            dbc.Col(accordions, width=12)
        ])
    ], fluid=True, className="bg-light pb-5")

# ---------------------------------------------------------
# 3. Interactive Callbacks (The Nervous System)
# ---------------------------------------------------------
@app.callback(
    Output('well-profile-graph', 'figure'),
    Input('hydrograph-chart', 'hoverData'),
    State('well-profile-graph', 'figure')
)
def sync_water_level(hover_data, well_fig):
    """Listens to the hydrograph hover events and updates the well profile water level."""
    if not hover_data: 
        return well_fig
        
    try:
        point_data = hover_data['points'][0]
        # Ensure we are extracting a valid numeric Y-axis elevation
        if 'y' in point_data and isinstance(point_data['y'], (int, float)):
            current_elevation = point_data['y']
            
            # Locate the designated water level trace and update its position
            for trace in well_fig['data']:
                if trace.get('name') == 'DynamicWaterLevel':
                    trace['y'] = [current_elevation, current_elevation, current_elevation]
                    break
        return well_fig
    except Exception as e:
        print(f"Hover synchronization error: {e}")
        return well_fig

# ---------------------------------------------------------
# 4. Pure API Application Bootstrapper
# ---------------------------------------------------------
async def build_dashboard_figures(site_code: str):
    """
    Executes the async CKAN API calls to fetch all necessary data,
    processes it, and builds the static Figure objects before the server starts.
    """
    print(f"Initiating parallel CKAN API requests for site: {site_code}...")
    
    # 1. Fire all independent network requests simultaneously
    station_task = get_station_info(site_code)
    gsp_task = get_records_by_attribute("gsp_monitoring", "SITE_CODE", site_code)
    msmt_task = get_measurements(site_code)
    #perf_task = get_perforation_data(site_code)
    prefix = site_code[:15]
    perf_sql = f'SELECT * FROM "{RESOURCES["perforations"]}" WHERE "site_code" LIKE \'{prefix}%\''
    perf_task = execute_sql_paginated(perf_sql)
    
    station_records, gsp_records, measurements_records, perf_records = await asyncio.gather(
        station_task, gsp_task, msmt_task, perf_task
    )

    # 2. Extract GSE for the well profile boundaries
    gse_val = "N/A"
    if station_records:
        try:
            gse_val = float(station_records[0].get('gse'))
        except (TypeError, ValueError):
            pass

    # 3. Standardize API perforation data to match the well_profile module's expected format
    screens_df = pd.DataFrame()
    if perf_records:
        screens_df = pd.DataFrame(perf_records)
        screens_df.rename(columns={
            'top_prf_int': 'TOP_PRF', 
            'bot_prf_int': 'BOT_PRF',
            'site_code': 'SITE_CODE'
        }, inplace=True)
        
        screens_df['TOP_PRF'] = pd.to_numeric(screens_df['TOP_PRF'], errors='coerce')
        screens_df['BOT_PRF'] = pd.to_numeric(screens_df['BOT_PRF'], errors='coerce')
        screens_df.dropna(subset=['TOP_PRF', 'BOT_PRF'], inplace=True)

    # 4. Construct the UI components
    print("Building UI components...")
    hydro_fig = await generate_interactive_hydrograph_logic(
        site_code=site_code,
        get_measurements_func=get_measurements,
        get_records_func=get_records_by_attribute,
        get_wy_func=get_water_years
    )
    
    well_fig = create_well_profile_figure(site_code, screens_df, gse_val)
    const_table = create_construction_table(screens_df) # Generate the well construction side table

    accordions = create_dashboard_accordions(
        site_code, station_records, gsp_records, measurements_records, perf_records
    )
    
    return hydro_fig, well_fig, const_table, accordions

def open_browser():
    webbrowser.open_new("http://127.0.0.1:8051")

if __name__ == '__main__':
    # Define the target well
    #target_site = "369604N1219650W003"
    target_site = "369558N1219720W002"
    
    # Listen to the terminal command for an argument
    if len(sys.argv) > 1:
        target_site = sys.argv[1]

    print(f"\n--- Booting Standalone Dashboard for {target_site} ---")

    # STEP 1: Fetch data and compile figures asynchronously
    hydro_figure, well_figure, const_table, dashboard_accordions = asyncio.run(build_dashboard_figures(target_site))
    
    # STEP 2: Assign the completed figures to the layout
    app.layout = serve_layout(hydro_figure, well_figure, const_table, dashboard_accordions)
    
    # Only open the browser in the main worker process, avoiding the double-tab bug
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        Timer(1, open_browser).start()
        
    # STEP 3: Launch the application
    print("Dashboard architecture fully initialized. Launching server at http://127.0.0.1:8051")
    app.run(debug=True, port=8051)