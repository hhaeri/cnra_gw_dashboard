// A console log so we can prove the browser successfully loaded this file
console.log("Custom Leaflet JS loaded successfully!");

// Define our own global namespace explicitly
window.customMap = {
    default: {
        drawDot: function (feature, latlng) {
            // 1. Draw your custom lightweight circle 
            const marker = L.circleMarker(latlng, {
                radius: 3,             // Dot size // Decreased from 4 to make them smaller
                fillColor: '#007bff',  // Crisp blue
                fillOpacity: 1,           // Made fully solid to compensate for smaller size

                color: 'transparent',      // Make the border completely invisible 
                opacity: 0,            // Double safety to ensure the border doesn't render
                weight: 10,              // Massive 15-pixel invisible buffer around the dot!
            });
            // 2. Build the HTML popup dynamically using the feature properties
            const p = feature.properties;

            // Only bind a popup if we actually passed the well data from Python
            if (p.site_code) {
                // Safely encode the name for the URL link
                const safe_name = encodeURIComponent(p.well_name);

                const popupHTML = `
                    <div style='font-family: sans-serif; min-width: 220px;'>
                        <h6 style='margin: 0px 0px 4px 0px; font-weight: bold;'>${p.well_name}</h6>
                        <p style='margin: 0px; font-size: 11px; color: #555;'><b>Basin:</b> ${p.basin_name}</p>
                        <p style='margin: 0px 0px 8px 0px; font-size: 11px; color: #555;'><b>County:</b> ${p.county_name}</p>
                        
                        <a href='/well-dashboard?id=${p.site_code}&name=${safe_name}' 
                           target='_blank' rel='noopener noreferrer'
                           style='display: block; background-color: #2c3e50; color: white; padding: 6px; 
                                  text-align: center; text-decoration: none; border-radius: 4px; font-size: 12px; font-weight: bold;'>
                           Open Hydrograph Analytics ↗
                        </a>
                    </div>
                `;

                marker.bindPopup(popupHTML);
            }

            return marker;
        }
    }
};