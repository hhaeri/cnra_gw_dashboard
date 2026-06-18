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

            if (p.site_code) {
                // 1. Explicitly bind the lightweight hover tooltip
                if (p.tooltip) {
                    marker.bindTooltip(p.tooltip);
                }

                const safe_name = encodeURIComponent(p.well_name);

                // 2. Create a dynamic color for the SGMA Badge (Teal for Rep, Gray for Non-Rep)
                const badgeColor = p.sgma_status === 'SGMA Representative' ? '#17a2b8' : '#6c757d';

                // 3. Inject the Site Code and SGMA Badge into the HTML
                const popupHTML = `
                    <div style='font-family: sans-serif; min-width: 240px;'>
                        <div style='margin-bottom: 6px;'>
                            <span style='background-color: ${badgeColor}; color: white; padding: 3px 6px; border-radius: 4px; font-size: 10px; font-weight: bold;'>${p.sgma_status}</span>
                        </div>
                        <h6 style='margin: 0px 0px 4px 0px; font-weight: bold;'>${p.well_name}</h6>
                        <p style='margin: 0px; font-size: 11px; color: #555;'><b>Site Code:</b> ${p.site_code}</p>
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