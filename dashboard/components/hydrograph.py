import tempfile
import webbrowser
import pandas as pd
import plotly.graph_objects as go

async def generate_interactive_hydrograph_logic(site_code: str, get_measurements_func, get_records_func, get_wy_func) -> str:
    """
    Core logic for generating an interactive Plotly hydrograph.
    Accepts the async data-fetching functions as injected dependencies.
    """
    # ---------------------------------------------------------
    # 1. Asynchronous Data Ingestion
    # ---------------------------------------------------------
    records = await get_measurements_func(site_code=site_code)
    if not records:
        return f"No measurement data found for site_code: {site_code}"

    df = pd.DataFrame(records)

    # Fetch dynamic water year data using the dedicated WY tool
    wy_records = await get_wy_func()
    wy_mapping = {}
    for r in wy_records:
        wy_str = str(r.get('WY', '')).split('.')[0]
        if wy_str.isdigit():
            raw_code = r.get('WYT', '').strip()
            mapping_dict = {"W": "Wet", "AN": "Normal", "BN": "Normal", "D": "Dry", "C": "Critical"}
            wy_mapping[int(wy_str)] = mapping_dict.get(raw_code, "Normal")

    # Fetch station metadata (MO, MT, Name)
    mo, mt, well_name = None, None, "Unknown Well"
    try:
        mo_records = await get_records_func("gsp_monitoring", "SITE_CODE", site_code)
        if mo_records:
            mo_val = mo_records[0].get("SMC_MO") or mo_records[0].get("smc_mo")
            mt_val = mo_records[0].get("SMC_MT") or mo_records[0].get("smc_mt")
            name_val = mo_records[0].get("WELL_NAME") or mo_records[0].get("well_name")
            
            if mo_val is not None: mo = float(mo_val)
            if mt_val is not None: mt = float(mt_val)
            if name_val: well_name = str(name_val)
    except Exception as e:
        print(f"Warning: Could not fetch metadata for {site_code}: {e}")

    # ---------------------------------------------------------
    # 2. Pre-processing & Analytics 
    # ---------------------------------------------------------
    df.columns = [str(c).lower().strip() for c in df.columns]
    date_col = 'msmt_date'
    gwe_col = 'gwe'

    if date_col not in df.columns or gwe_col not in df.columns:
        return f"Error: Dataset is missing required columns '{date_col}' or '{gwe_col}'."

    df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
    df[gwe_col] = pd.to_numeric(df[gwe_col], errors='coerce')
    df = df.dropna(subset=[date_col, gwe_col]).sort_values(by=date_col)

    if df.empty:
        return f"Error: No valid numeric GWE or date data available to plot."

    # Dynamically apply Water Year from the live API mapping
    df['water_year'] = df[date_col].apply(lambda d: d.year + 1 if d.month >= 10 else d.year)
    df['wy_type'] = df['water_year'].map(wy_mapping).fillna("Normal")

    df = df.set_index(date_col)
    df['ma_5yr'] = df[gwe_col].rolling('1825D', min_periods=1).mean()
    df = df.reset_index()

    # ---------------------------------------------------------
    # 2b. Water Year Minimums & 5-Yr Trend
    # ---------------------------------------------------------
    # Group the in-memory data by our strictly defined water year to find the absolute lowest elevation
    df_lows = df.groupby('water_year')[gwe_col].min().reset_index()
    df_lows.rename(columns={gwe_col: 'wy_min_gwe'}, inplace=True)
    
    # Anchor the data point to October 1st so it plots cleanly on the X-axis gridlines
    df_lows['plot_date'] = pd.to_datetime((df_lows['water_year'] - 1).astype(int).astype(str) + '-10-01')

    # Calculate the 5-year moving average on these minimums
    df_lows = df_lows.set_index('plot_date')
    df_lows['min_ma_5yr'] = df_lows['wy_min_gwe'].rolling('1825D', min_periods=1).mean()
    df_lows = df_lows.reset_index()

    # ---------------------------------------------------------
    # 3. Plotly Visualization
    # ---------------------------------------------------------
    fig = go.Figure()

    # ADD REAL DATA TRACES FIRST
    fig.add_trace(go.Scatter(
        x=df[date_col], y=df[gwe_col], 
        mode='lines+markers', name='Measurements', 
        line=dict(color='gray', width=1), marker=dict(size=4), opacity=0.8
    ))
    
    fig.add_trace(go.Scatter(
        x=df[date_col], y=df['ma_5yr'], 
        mode='lines', name='5-Yr Moving Avg', 
        line=dict(color='darkblue', width=3, dash='dot'), 
            marker=dict(size=5), opacity=0.9
    ))

    # Add Annual Water Year Min 5-Yr MA Trace
    if not df_lows.empty and 'min_ma_5yr' in df_lows.columns:
        fig.add_trace(go.Scatter(
            x=df_lows['plot_date'], y=df_lows['min_ma_5yr'], 
            mode='lines+markers', name='5-Yr MA of Annual Min', 
            line=dict(color='darkblue', width=3), opacity=0.9
        ))

    # Apply Background Shading for Water Years & Dummy Legends
    # By using RGBA strings, Plotly is forced to render the exact same transparency 
    # in both the graph background and the legend swatches.
    wy_rgba = {
        "Wet": "rgba(0, 0, 139, 0.20)",          # DarkBlue at 20%
        "Normal": "rgba(70, 130, 180, 0.15)", # SteelBlue at 15%
        "Dry": "rgba(240, 128, 128, 0.15)",         # LightCoral at 15%
        "Critical": "rgba(139, 0, 0, 0.20)"         # DarkRed at 20%
    }

    # # 1. Add an invisible trace to act as the "Water Year Type:" text in the legend
    # fig.add_trace(go.Scatter(
    #     x=[None], y=[None], name="<b>Water Year Type:</b>",
    #     mode="markers", marker=dict(color="rgba(0,0,0,0)", size=0),
    #     showlegend=True
    # ))

    # 2. Force the exact legend order
    ordered_types = ["Wet", "Normal", "Dry", "Critical"]

    for wy_type in ordered_types:
        fig.add_trace(go.Bar(
            x=[None], y=[None], name=wy_type,
            legend="legend2", # Forces this trace into the second legend
            marker=dict(color=wy_rgba[wy_type], line=dict(color='gray', width=1)),
            showlegend=True
        ))

    # 3. Draw the background rectangles over the continuous timeline
    # Find the absolute first and last water years in the dataset
    min_wy = int(df['water_year'].min())
    max_wy = int(df['water_year'].max())

    # Loop through every single year in that range, regardless of missing measurements
    for wy in range(min_wy, max_wy + 1):
        # Look up the water year type from your master dictionary, defaulting to "Normal"
        wy_type = wy_mapping.get(wy, "Normal")
        
        # Only draw a background if it's a recognized water year type in your RGBA dict
        if wy_type in wy_rgba:
            start_date = f"{wy-1}-10-01"
            end_date = f"{wy}-09-30"
            fig.add_vrect(
                x0=start_date, x1=end_date, 
                fillcolor=wy_rgba[wy_type], 
                layer="below", line_width=0
            )

    # Add Thresholds
    if mt is not None:
        fig.add_hline(y=mt, line_dash="dash", line_color="red", line_width=2.5)
        fig.add_annotation(x=1.02, y=mt, xref="paper", yref="y", text=f"<b>Min Threshold ({mt} ft)</b>", showarrow=False, xanchor="left", font=dict(color="red", size=12))
        
    if mo is not None:
        fig.add_hline(y=mo, line_dash="dashdot", line_color="green", line_width=2.5)
        fig.add_annotation(x=1.02, y=mo, xref="paper", yref="y", text=f"<b>Measurable Obj ({mo} ft)</b>", showarrow=False, xanchor="left", font=dict(color="green", size=12))

    # Format Layout
    fig.update_layout(
        title=f"<b>Groundwater Elevation: {well_name} ({site_code})</b>",
        yaxis_title="Elevation (ft amsl)", plot_bgcolor='white', hovermode="closest",
        legend=dict(
            # title=dict(text="<b>Water Year Type:</b> ", side="left"), # ADDED PREFIX TITLE
            orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5, 
            bordercolor="black", borderwidth=1, traceorder="normal"
        ),
        legend2=dict(
            title=dict(text="<b>Water Year Type:</b> ", side="left"), 
            orientation="h", yanchor="top", y=-0.28, xanchor="center", x=0.5, 
            bordercolor="black", borderwidth=1, traceorder="normal"
        ), 
        margin=dict(r=20, b=150) # Increased bottom margin to fit the second box
    )
    
    # Force X-axis to DateTime and align ticks to October 1st
    fig.update_xaxes(
        type='date',         
        showgrid=True, gridwidth=1, gridcolor='LightGray',
        tickmode='linear',
        tick0='1980-10-01',  
        dtick='M12',         
        tickformat="%b %Y",  
        tickangle=-90        
    )
    
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='LightGray')

    # # ---------------------------------------------------------
    # # 4. Ephemeral Display
    # # ---------------------------------------------------------
    # temp_html = tempfile.NamedTemporaryFile(delete=False, suffix=".html")
    # temp_filepath = temp_html.name
    # temp_html.close()

    # fig.write_html(temp_filepath, config={'displaylogo': False})
    # webbrowser.open(f"file://{temp_filepath}")

    # return f"SUCCESS: Interactive hydrograph for {site_code} has been generated."
    # Return the raw Plotly figure object instead of an HTML string
    return fig