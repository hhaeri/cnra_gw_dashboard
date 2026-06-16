from dash import Dash, html

app = Dash(__name__)

app.layout = html.Div([
    html.H1("SUCCESS!", style={'color': 'green'}),
    html.P("Your Mac and your browser are perfectly communicating with Python.")
])

if __name__ == '__main__':
    print("Booting minimal test server on Port 8050...")
    app.run(host = '0.0.0.0', debug=True, port = 8050)