# 💧 CNRA Groundwater Dashboard & MCP Server

A lightweight Model Context Protocol (MCP) data pipeline and interactive Plotly Dash dashboard for fetching, rendering, and analyzing California Natural Resources Agency (CNRA) SGMA groundwater telemetry.

This repository features a decoupled microservices architecture, isolating the data-fetching engine (MCP API) from the visual rendering front-end (Dashboard).

---

## 🏗️ Project Architecture

This is a Monorepo containing two distinct modules:

* **`/mcp_api` (The Data Engine):** A lightweight server that interfaces asynchronously with CNRA and CKAN APIs to fetch groundwater elevation, station data, and well perforations.
* **`/dashboard` (The User Interface):** A Plotly Dash application that imports data from the `mcp_api` to generate interactive hydrographs and well construction profiles.

---

## 🚀 Installation & Setup

Because this project isolates the backend and frontend, it utilizes two separate `requirements.txt` files. 

**1. Clone the repository**
```bash
git clone [https://github.com/yourusername/cnra-groundwater-dashboard.git](https://github.com/yourusername/cnra-groundwater-dashboard.git)
cd cnra-groundwater-dashboard

```

**2. Install the backend (MCP) dependencies**

```bash
pip install -r mcp_api/requirements.txt

```

**3. Install the frontend (Dashboard) dependencies**

```bash
pip install -r dashboard/requirements.txt

```

*(Note: If you are running this locally on a single machine, you can install both into the same Python virtual environment).*

---

## 🖥️ Using the Dashboards

This repository offers two different ways to explore groundwater data visually. **Always run these scripts from the root directory of the project** so the Python path routing works correctly.

### 1. The Dynamic Explorer (`app.py`)

This is a "Just-In-Time" interactive dashboard. It boots up instantly and provides a searchable dropdown menu of active SGMA monitoring wells. When you select a well, the app dynamically reaches out to the CNRA API and loads the visuals on the fly.

**How to run:**

```bash
python dashboard/app.py

```

* **Access:** `http://127.0.0.1:8050`
* **Best for:** Broad exploration, quickly clicking through different wells, and general monitoring.

### 2. The Standalone Deep-Dive (`app_standalone.py`)

This is a "Pre-Built" CLI tool. It fetches all the data for a specific well in your terminal *before* booting the web server. Once the data is compiled, it launches a highly responsive, zero-latency dashboard.

**How to run:**

```bash
python dashboard/app_standalone.py

```

* **Access:** `http://127.0.0.1:8051`
* **Best for:** Deep-dive analysis on a single well where you want maximum UI performance without waiting for network loading spinners.

---

## 📊 Dashboard Components

Once you launch either dashboard, you will have access to three primary interactive components:

* **Interactive Hydrograph:** A dynamic time-series chart showing groundwater elevations over time. Hovering over data points on this graph automatically syncs with the Well Profile Sketch.
* **Well Profile Sketch & Construction Table:** A visual representation of the borehole, showing ground surface elevation (GSE) and screen intervals (perforations). As you hover over the Hydrograph, the dynamic water level in the sketch updates in real-time.
* **Metadata Accordions:** Expandable data tables at the bottom of the page containing raw datasets, station information, and GSP monitoring details.

---

## ⚙️ Using the MCP Server Tools

The `/mcp_api/server.py` file acts as the central data nervous system. While it currently powers the Dash UI, it is formatted to be consumed by an AI Agent or LLM via the Model Context Protocol.

The server exposes the following core tools:

* **`get_station_info(site_code)`**: Fetches the physical metadata for a specific well (latitude, longitude, total depth, ground surface elevation).
* **`get_measurements(site_code)`**: Retrieves the complete historical time-series of groundwater level measurements for a specific well.
* **`get_records_by_attribute(resource_name, attribute, value)`**: A flexible query tool to fetch filtered data from specific CNRA datasets (like the GSP monitoring network).
* **`get_water_years()`**: Generates California Water Year classifications for time-series overlays.
* **`execute_sql_paginated(sql_query)`**: A raw SQL execution tool for bypassing standard endpoints and querying the CKAN datastore directly.

### To use these tools in your own Python scripts:

Because the `mcp_api` acts as a local package, you can import these data fetchers into any Python script running from the root directory:

```python
import asyncio
from mcp_api.server import get_measurements

async def test_fetch():
    data = await get_measurements("369604N1219650W003")
    print(data)

asyncio.run(test_fetch())

```
