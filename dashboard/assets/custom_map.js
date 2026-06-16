// A console log so we can prove the browser successfully loaded this file
console.log("Custom Leaflet JS loaded successfully!");

// Define our own global namespace explicitly
window.customMap = {
    default: {
        drawDot: function (feature, latlng) {
            return L.circleMarker(latlng, {
                radius: 3,             // Dot size // Decreased from 4 to make them smaller
                fillColor: '#007bff',  // Crisp blue
                fillOpacity: 1,           // Made fully solid to compensate for smaller size

                color: 'transparent',      // Make the border completely invisible 
                opacity: 0,            // Double safety to ensure the border doesn't render
                weight: 10,              // Massive 15-pixel invisible buffer around the dot!
            });
        }
    }
};
