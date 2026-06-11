import dash_bootstrap_components as dbc
from dash import html, dash_table
import pandas as pd
import numpy as np

def create_dashboard_accordions(site_code: str, station_records: list, gsp_records: list, measurements_records: list, perf_records: list) -> dbc.Accordion:
    """
    Generates USGS-style collapsible accordion tables for Well Summary, 
    Water Level Statistics, and Raw Water Level Data.
    """
    # ---------------------------------------------------------
    # 1. Safe Data Extraction
    # ---------------------------------------------------------
    station_data = station_records[0] if station_records else {}
    gsp_data = gsp_records[0] if gsp_records else {}
    
    # Process Measurements for Stats and Raw Tables
    df_msmt = pd.DataFrame(measurements_records)
    if not df_msmt.empty:
        df_msmt.columns = [str(c).lower().strip() for c in df_msmt.columns]
        df_msmt['msmt_date'] = pd.to_datetime(df_msmt['msmt_date'], errors='coerce')
        df_msmt['gwe'] = pd.to_numeric(df_msmt.get('gwe'), errors='coerce')
        df_msmt = df_msmt.dropna(subset=['msmt_date', 'gwe']).sort_values('msmt_date')

    # ---------------------------------------------------------
    # 2. Build Summary Table Data
    # ---------------------------------------------------------
    # Format screen intervals directly from the API perforation data
    screens = "Data Unavailable"
    if perf_records:
        intervals = [f"{r.get('top_prf_int', 'N/A')} to {r.get('bot_prf_int', 'N/A')} ft" for r in perf_records]
        screens = f"{len(perf_records)} screen(s): " + " | ".join(intervals)

    summary_rows = [
        {"Property": "Site Name", "Value": station_data.get('well_name', 'Unknown')},
        {"Property": "Site Code", "Value": site_code},
        {"Property": "Well Type", "Value": station_data.get('well_type', 'Unknown')},
        {"Property": "Well Use", "Value": station_data.get('well_use', 'Unknown')},
        {"Property": "Latitude / Longitude", "Value": f"{station_data.get('latitude', 'N/A')}, {station_data.get('longitude', 'N/A')}"},
        {"Property": "Ground Surface Elevation (GSE)", "Value": f"{station_data.get('gse', 'N/A')} ft"},
        {"Property": "Well Depth", "Value": f"{station_data.get('well_depth', 'N/A')} ft"},
        {"Property": "Basin Name", "Value": station_data.get('basin_name', 'N/A')},
        {"Property": "Principal Aquifer", "Value": gsp_data.get('PRINCIPAL_AQUIFER') or gsp_data.get('principal_aquifer', 'None Reported')},
        {"Property": "Screen Intervals", "Value": screens},
    ]

    summary_table = dbc.Table.from_dataframe(pd.DataFrame(summary_rows), striped=True, bordered=True, hover=True, size="sm")

    # ---------------------------------------------------------
    # 3. Build Statistics Table Data
    # ---------------------------------------------------------
    if not df_msmt.empty:
        first_date = df_msmt['msmt_date'].min()
        last_date = df_msmt['msmt_date'].max()
        years_record = (last_date - first_date).days / 365.25

        stats_dict = {
            "Lowest Elevation (ft)": f"{df_msmt['gwe'].min():.2f}",
            "Median Elevation (ft)": f"{df_msmt['gwe'].median():.2f}",
            "Highest Elevation (ft)": f"{df_msmt['gwe'].max():.2f}",
            "First Measurement": first_date.strftime('%Y-%m-%d'),
            "Last Measurement": last_date.strftime('%Y-%m-%d'),
            "Total Measurements": len(df_msmt),
            "Years of Record": f"{years_record:.1f}",
            "Latest Value (ft)": f"{df_msmt['gwe'].iloc[-1]:.2f}"
        }
        stats_table = dbc.Table.from_dataframe(pd.DataFrame([stats_dict]), striped=True, bordered=True, hover=True, size="sm")
    else:
        stats_table = html.P("No valid measurement data available for statistics.")

    # ---------------------------------------------------------
    # 4. Build Raw Water Levels Data Table
    # ---------------------------------------------------------
    if not df_msmt.empty:
        display_df = df_msmt.copy()
        display_df['msmt_date'] = display_df['msmt_date'].dt.strftime('%Y-%m-%d %H:%M')
        
        # Filter strictly to the relevant columns
        target_cols = ['msmt_date', 'gwe', 'gse_gwe', 'wlm_gse', 'wlm_rpe']
        existing_cols = [c for c in target_cols if c in display_df.columns]
        display_df = display_df[existing_cols]
        
        # Clean column headers
        col_names = {"msmt_date": "Date", "gwe": "Groundwater Elevation (ft amsl)", "gse_gwe": "Depth to Groundwater (ft below land surface)", "wlm_gse": "Ground Surface Elevation (GSE) (ft amsl)", "wlm_rpe": "Reference Point Elevation (RPE) (ft amsl)"}

        # Use Dash DataTable for built-in pagination on the raw data
        raw_table = dash_table.DataTable(
            data=display_df.to_dict('records'),
            columns=[{"name": col_names.get(i, i), "id": i} for i in display_df.columns],
            page_size=30,
            sort_action="native", # Enables clicking headers to sort
            style_table={'overflowX': 'auto'},
            style_cell={'textAlign': 'left', 'padding': '10px', 'fontFamily': 'sans-serif'},
            style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold'},
        )
    else:
        raw_table = html.P("No raw measurement data available.")

    # ---------------------------------------------------------
    # 5. Assemble and Return the Accordion
    # ---------------------------------------------------------
    return dbc.Accordion([
        dbc.AccordionItem(summary_table, title="Well Summary & Construction", item_id="item-summary"),
        dbc.AccordionItem(stats_table, title="Overall Water Level Statistics", item_id="item-stats"),
        dbc.AccordionItem(raw_table, title="Raw Water Levels", item_id="item-raw"),
    ], start_collapsed=False, always_open=True, className="mt-4 shadow-sm")