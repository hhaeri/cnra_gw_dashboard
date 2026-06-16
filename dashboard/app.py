import os
import dash
import dash_bootstrap_components as dbc
import webbrowser
from threading import Timer

# 1. Dynamically locate the exact folder where app.py lives
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 2. Tell Dash to look exactly inside the 'assets' folder next to app.py
ASSETS_PATH = os.path.join(BASE_DIR, "assets")

# 3. Pass the explicit path into the Dash initialization
app = dash.Dash(
    __name__, 
    use_pages=True, 
    external_stylesheets=[dbc.themes.FLATLY],
    suppress_callback_exceptions=True,
    assets_folder=ASSETS_PATH
)

server = app.server

# ---------------------------------------------------------
# 2. The Global Router Shell
# ---------------------------------------------------------
# This dynamically loads whichever page the user is on (map or well dashboard)
def render_production_layout():
    return dbc.Container([
        dash.page_container 
    ], fluid=True, className="p-0")

app.layout = render_production_layout

# ---------------------------------------------------------
# 3. Local Server Bootstrapper
# ---------------------------------------------------------
def open_browser():
    webbrowser.open_new("http://127.0.0.1:8050")

if __name__ == '__main__':
    # Only open the browser in the local main worker process
    if os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        Timer(1, open_browser).start()

    print("Dashboard architecture fully initialized. Launching local server at http://127.0.0.1:8050")
    app.run(debug=True, port=8050)



# if __name__ == '__main__':
#     # Since we are disabling the reloader, the app will only boot exactly once.
#     # We no longer need the WERKZEUG environment check!
#     Timer(1, open_browser).start()

#     print("Dashboard architecture fully initialized. Launching local server at http://127.0.0.1:8888")
    
#     # Add use_reloader=False to stop the API double-download --> this will also turn off the auto open and load the browser page
#     app.run(host='0.0.0.0', debug=True, port=8888, use_reloader=False)