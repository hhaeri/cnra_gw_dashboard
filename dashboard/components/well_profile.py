import plotly.graph_objects as go
import pandas as pd
import dash_bootstrap_components as dbc
from dash import html

def create_well_profile_figure(site_code: str, screens_df: pd.DataFrame, gse_val: float, current_wl: float = None) -> go.Figure:
    """
    Generates a vertical Plotly figure of the well borehole, casing, and screens.
    Includes a dynamic water level trace intended to be updated by a Dash callback.
    """
    fig = go.Figure()
    
    # 1. Determine Y-Axis Boundaries (handling both depth and elevation formats)
    if not screens_df.empty:
        max_top = screens_df['TOP_PRF'].max()
        min_bot = screens_df['BOT_PRF'].min()
        
        # If TOP < BOT, data is in Depth Below Ground Surface. If TOP > BOT, data is Elevation.
        is_depth = screens_df['TOP_PRF'].iloc[0] < screens_df['BOT_PRF'].iloc[0]
        
        if is_depth:
            # Convert depth to elevation using GSE
            screens_df['TOP_ELEV'] = gse_val - screens_df['TOP_PRF']
            screens_df['BOT_ELEV'] = gse_val - screens_df['BOT_PRF']
        else:
            screens_df['TOP_ELEV'] = screens_df['TOP_PRF']
            screens_df['BOT_ELEV'] = screens_df['BOT_PRF']
            
        y_max = gse_val + 20 if isinstance(gse_val, (int, float)) else screens_df['TOP_ELEV'].max() + 20
        y_min = screens_df['BOT_ELEV'].min() - 20
    else:
        y_max, y_min = 100, -100 # Fallback

    # 2. Draw Ground Surface Elevation (GSE)
    if isinstance(gse_val, (int, float)):
        fig.add_shape(
            type="line", x0=-2, x1=2, y0=gse_val, y1=gse_val,
            line=dict(color="#4B5563", width=4)
        )
        fig.add_annotation(
            x=-2.2, y=gse_val, text=f"GSE: +{gse_val:.2f}'", 
            showarrow=False, xanchor="right", font=dict(size=11, color="#4B5563")
        )

    # 3. Draw the Main Casing (Background Pipe)
    fig.add_shape(
        type="rect", x0=-0.5, x1=0.5, y0=y_max - 20, y1=y_min + 10,
        fillcolor="#F3F4F6", line=dict(color="#D1D5DB", width=1), layer="below"
    )

    # 4. Draw Screens and Labels
    if not screens_df.empty:
        for _, row in screens_df.iterrows():
            s_code = row['SITE_CODE']
            s_name = str(row['WELL_NAME']) if pd.notna(row.get('WELL_NAME')) else s_code
            top_elev = row['TOP_ELEV']
            bot_elev = row['BOT_ELEV']
            
            is_active = (s_code == site_code)
            color = "#2563EB" if is_active else "#9CA3AF"
            opacity = 1.0 if is_active else 0.5
            
            # Screen Rectangle
            fig.add_shape(
                type="rect", x0=-0.6, x1=0.6, y0=bot_elev, y1=top_elev,
                fillcolor=color, opacity=opacity, line_width=0
            )
            
            # Label
            mid_y = (top_elev + bot_elev) / 2
            #label_text = f"<b>{s_name}</b><br>({row['TOP_PRF']:.1f}' to {row['BOT_PRF']:.1f}')"
            label_text = f"<b>{s_name}</b>" # Removed the depth string
            fig.add_annotation(
                x=0.8, y=mid_y, text=label_text, showarrow=False, 
                xanchor="left", font=dict(size=10, color=color)
            )

    # 5. THE DYNAMIC WATER LEVEL TRACE
    # This is the crucial part. We create a dedicated trace that Dash will target and update.
    # We use a distinct blue line and a downward triangle to mimic the USGS UI.
    start_wl = current_wl if current_wl is not None else y_max # Default to hiding it at the top
    
    fig.add_trace(go.Scatter(
        x=[-1.5, 0, 1.5], y=[start_wl, start_wl, start_wl],
        mode="lines+markers", name="DynamicWaterLevel",
        line=dict(color="#0ea5e9", width=3, dash="dash"),
        marker=dict(symbol=["line-ew", "triangle-down", "line-ew"], size=[0, 12, 0], color="#0ea5e9"),
        hoverinfo="skip", showlegend=False
    ))

    # 6. Formatting the Plotly Canvas to look like an embedded UI element
    fig.update_layout(
        title=dict(text="<b>Borehole Profile</b>", font=dict(size=14), x=0.5, xanchor="center"),
        xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, range=[-3, 3]),
        yaxis=dict(showgrid=True, gridcolor="#E5E7EB", title="Elevation (ft amsl)"),
        plot_bgcolor="white",
        margin=dict(l=50, r=100, t=40, b=20),
        height=600  # Fixed height ensures it sits nicely next to the hydrograph
    )
    
    return fig


def create_construction_table(screens_df: pd.DataFrame):
    """Generates the USGS-style side table for screen intervals."""
    if screens_df.empty:
        return html.Div("No lithology/construction data.", className="text-muted p-3")

    # Sort top down
    df_sorted = screens_df.sort_values('TOP_PRF', ascending=True)

    table_rows = []
    for _, row in df_sorted.iterrows():
        # Clean up the node name for display
        node_name = str(row.get('WELL_NAME', row['SITE_CODE']))
        if " " in node_name:
            node_name = node_name.split(" ")[-1]

        table_rows.append(html.Tr([
            html.Td(node_name, style={"fontSize": "11px", "fontWeight": "bold"}),
            html.Td(f"{row['TOP_PRF']:.1f} - {row['BOT_PRF']:.1f} ft", style={"fontSize": "11px"})
        ]))

    table_header = [html.Thead(html.Tr([html.Th("Screen/Node"), html.Th("Depth")]))]
    table_body = [html.Tbody(table_rows)]

    return dbc.Table(table_header + table_body, bordered=True, hover=True, size="sm", className="mt-5 bg-white")