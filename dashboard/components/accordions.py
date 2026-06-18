import dash_bootstrap_components as dbc
from dash import html, dash_table
import pandas as pd
import numpy as np

def create_dashboard_accordions(site_code: str, station_records: list, gsp_records: list, measurements_records: list, perf_records: list, is_representative: bool) -> dbc.Accordion:
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

    # # ---------------------------------------------------------
    # # 5. Assemble and Return the Accordion
    # # ---------------------------------------------------------
    # return dbc.Accordion([
    #     dbc.AccordionItem(summary_table, title="Well Summary & Construction", item_id="item-summary"),
    #     dbc.AccordionItem(stats_table, title="Overall Water Level Statistics", item_id="item-stats"),
    #     dbc.AccordionItem(raw_table, title="Raw Water Levels", item_id="item-raw"),
    # ], start_collapsed=False, always_open=True, className="mt-4 shadow-sm")


    # ---------------------------------------------------------
    # 5. Assemble the Base Accordion Items
    # ---------------------------------------------------------
    accordion_items = [
        dbc.AccordionItem(summary_table, title="Well Summary & Construction", item_id="item-summary"),
        dbc.AccordionItem(stats_table, title="Overall Water Level Statistics", item_id="item-stats"),
        dbc.AccordionItem(raw_table, title="Raw Water Levels", item_id="item-raw"),
    ]

    # ---------------------------------------------------------
    # 6. Inject SGMA Non-Representative Notice (If Applicable)
    # ---------------------------------------------------------
    # Utilize the dataframe we already built to get the count
    total_measurements = len(df_msmt) if not df_msmt.empty else 0
    prog = station_data.get('monitoring_program', 'Unknown')

    if not is_representative:

        non_rep_metrics_ui = dbc.AccordionItem([
            html.P("This well is not actively utilized as a representative monitoring site under the Sustainable Groundwater Management Act (SGMA).", className="text-muted mb-3"),
            dbc.Row([
                dbc.Col([
                    html.H6("Historical Telemetry Count", className="fw-bold mb-1"),
                    html.H4(f"{total_measurements:,}", className="text-primary")
                ], width=4),
                dbc.Col([
                    html.H6("Monitoring Program", className="fw-bold mb-1"),
                    html.P(prog)
                ], width=4)
            ], className="bg-light p-3 rounded border")
        ], title="SGMA Representative Well Metrics", item_id="item-non-rep")
        
        # Insert this item at the top of the accordion list for immediate visibility
        accordion_items.insert(1, non_rep_metrics_ui)

    else:
        # 1. Safely extract all SMC data from the gsp_records
        # Using .get() for both upper and lowercase handles API inconsistencies
        smc_mt = gsp_data.get('SMC_MT') or gsp_data.get('smc_mt', 'N/A')
        smc_mo = gsp_data.get('SMC_MO') or gsp_data.get('smc_mo', 'N/A')
        smc_im5 = gsp_data.get('SMC_IM_5_YR') or gsp_data.get('smc_im_5_yr', 'N/A')
        smc_im10 = gsp_data.get('SMC_IM_10_YR') or gsp_data.get('smc_im_10_yr', 'N/A')
        smc_im15 = gsp_data.get('SMC_IM_15_YR') or gsp_data.get('smc_im_15_yr', 'N/A')
        smc_start = gsp_data.get('SMC_START_DATE') or gsp_data.get('smc_start_date', 'N/A')

        # Format helper (adds 'ft' if the value exists)
        def fmt_ft(val):
            return f"{val} ft" if val != 'N/A' and val is not None else "N/A"

        # 2. Build the UI Layout
        rep_metrics_ui = dbc.AccordionItem([
            html.P("✅ This well is actively utilized as a representative monitoring site under the Sustainable Groundwater Management Act (SGMA).", className="text-success fw-bold mb-3"),
            
            html.Div([
                # Row 1: General Stats & Start Date
                dbc.Row([
                    dbc.Col([
                        html.H6("Historical Telemetry", className="fw-bold text-muted mb-1", style={"fontSize": "0.85rem"}),
                        html.H5(f"{total_measurements:,}", className="text-success mb-0")
                    ], width=4),
                    dbc.Col([
                        html.H6("Monitoring Program", className="fw-bold text-muted mb-1", style={"fontSize": "0.85rem"}),
                        html.P(prog, className="mb-0")
                    ], width=4),
                    dbc.Col([
                        html.H6("SMC Start Date", className="fw-bold text-muted mb-1", style={"fontSize": "0.85rem"}),
                        html.P(str(smc_start), className="mb-0")
                    ], width=4)
                ], className="mb-3 pb-3 border-bottom"),
                
                # Row 2: Primary Criteria (MT and MO)
                dbc.Row([
                    dbc.Col([
                        html.H6("Minimum Threshold (MT)", className="fw-bold mb-1", style={"fontSize": "0.85rem", "color": "#dc3545"}), # Red text for MT
                        html.H5(fmt_ft(smc_mt), className="mb-0") 
                    ], width=6),
                    dbc.Col([
                        html.H6("Measurable Objective (MO)", className="fw-bold mb-1", style={"fontSize": "0.85rem", "color": "#0d6efd"}), # Blue text for MO
                        html.H5(fmt_ft(smc_mo), className="mb-0") 
                    ], width=6)
                ], className="mb-3 pb-3 border-bottom"),

                # Row 3: Interim Milestones
                html.H6("Interim Milestones", className="fw-bold text-muted mb-2", style={"fontSize": "0.85rem"}),
                dbc.Row([
                    dbc.Col([
                        html.Small("5-Year", className="text-muted d-block"),
                        html.Span(fmt_ft(smc_im5), className="fw-bold")
                    ], width=4),
                    dbc.Col([
                        html.Small("10-Year", className="text-muted d-block"),
                        html.Span(fmt_ft(smc_im10), className="fw-bold")
                    ], width=4),
                    dbc.Col([
                        html.Small("15-Year", className="text-muted d-block"),
                        html.Span(fmt_ft(smc_im15), className="fw-bold")
                    ], width=4),
                ])
            ], className="bg-light p-3 rounded border border-success")
        ], title="SGMA Representative Well Metrics", item_id="item-rep")
        
        accordion_items.insert(1, rep_metrics_ui)
    # else:
    #     # THE NEW: Representative Accordion!
    #     rep_metrics_ui = dbc.AccordionItem([
    #         html.P("✅ This well is actively utilized as a representative monitoring site under the Sustainable Groundwater Management Act (SGMA).", className="text-success fw-bold mb-3"),
    #         dbc.Row([
    #             dbc.Col([
    #                 html.H6("Historical Telemetry Count", className="fw-bold mb-1"),
    #                 html.H4(f"{total_measurements:,}", className="text-success")
    #             ], width=4),
    #             dbc.Col([
    #                 html.H6("Monitoring Program", className="fw-bold mb-1"),
    #                 html.P(prog)
    #             ], width=4)
    #         ], className="bg-light p-3 rounded border border-success")
    #     ], title="SGMA Representative Well Metrics", item_id="item-rep")
        
    #     accordion_items.insert(0, rep_metrics_ui)

    # ---------------------------------------------------------
    # 7. Return the Final UI Component
    # ---------------------------------------------------------
    return dbc.Accordion(accordion_items, start_collapsed=False, always_open=True, className="mt-4 shadow-sm")