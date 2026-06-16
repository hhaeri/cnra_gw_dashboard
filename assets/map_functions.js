window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, latlng) {
            return L.circleMarker(latlng, {
                radius: 4,             // Size of the dot
                fillColor: '#007bff',  // Bootstrap primary blue
                color: 'white',        // Clean white border
                weight: 1,             // Border thickness
                fillOpacity: 0.8       // Slight transparency
            });
        }
    }
});