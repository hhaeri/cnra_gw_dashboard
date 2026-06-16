window.dashExtensions = Object.assign({}, window.dashExtensions, {
    default: {
        function0: function(feature, latlng) {
            return L.circleMarker(latlng, {
                radius: 4,
                fillColor: '#007bff', // Crisp blue
                color: '#ffffff', // White border
                weight: 0.5,
                fillOpacity: 0.8
            });
        }
    }
});