window.onerror = function(message, source, lineno, colno, error) {
    console.error('An error occurred:', message, 'at', source, 'line', lineno);
    return false;
};

console.log('script.js loaded');

var map, drawnItems;

document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM fully loaded and parsed');
    initializeMap();
    setupEventListeners();
});

function initializeMap() {
    console.log('Initializing map');
    var mapElement = document.getElementById('map');
    console.log('Map element:', mapElement);
    
    if (!mapElement) {
        console.error('Map element not found');
        return;
    }
    
    try {
        console.log('Creating map object');
        map = L.map('map').setView([51.505, -0.09], 13);
        console.log('Map object created:', map);
        
        console.log('Adding tile layer');
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '© OpenStreetMap contributors'
        }).addTo(map);
        console.log('Tile layer added to map');

        // Initialize Leaflet.draw
        drawnItems = new L.FeatureGroup();
        map.addLayer(drawnItems);

        var drawControl = new L.Control.Draw({
            draw: {
                polygon: true,
                polyline: false,
                rectangle: true,
                circle: false,
                marker: false,
                circlemarker: false
            },
            edit: {
                featureGroup: drawnItems,
                remove: true
            }
        });
        map.addControl(drawControl);

        // Event listener for when a shape is drawn
        map.on(L.Draw.Event.CREATED, function (event) {
            drawnItems.clearLayers(); // Clear previous shapes
            var layer = event.layer;
            drawnItems.addLayer(layer);
            updateAreaInfo(layer);
        });

        map.on(L.Draw.Event.EDITED, function (event) {
            var layers = event.layers;
            layers.eachLayer(function (layer) {
                updateAreaInfo(layer);
            });
        });

        map.on(L.Draw.Event.DELETED, function (event) {
            document.getElementById('areaInfo').innerHTML = '';
            document.getElementById('areaInfo').dataset.coordinates = '';
        });

        console.log('Map initialization complete');
    } catch (error) {
        console.error('Error initializing map:', error);
    }
}

function updateAreaInfo(layer) {
    var area = L.GeometryUtil.geodesicArea(layer.getLatLngs()[0]);
    var areaInKm = (area / 1000000).toFixed(2);
    var bounds = layer.getBounds();
    var coordinates = [
        bounds.getSouthWest().lat,
        bounds.getSouthWest().lng,
        bounds.getNorthEast().lat,
        bounds.getNorthEast().lng
    ].join(',');
    document.getElementById('areaInfo').innerHTML = `Selected Area: ${areaInKm} km²`;
    document.getElementById('areaInfo').dataset.coordinates = coordinates;
}

function analyzeTreeImage(imageFile, confidenceThreshold, selectedArea = null) {
    console.log('Analyzing tree image:', { imageFile, confidenceThreshold, selectedArea });
    // Show processing animation
    document.getElementById('processingAnimation').style.display = 'block';

    // Prepare the data to send
    var formData = new FormData();
    formData.append('conf', confidenceThreshold);

    let url;
    if (imageFile) {
        formData.append('image', imageFile);
        url = '/process_image';
    } else if (selectedArea) {
        formData.append('coordinates', selectedArea);
        url = '/process_area';
    } else {
        console.error('Neither image file nor selected area provided');
        alert('Please select an image or an area on the map.');
        return;
    }

    // Send the request to the server
    fetch(url, {
        method: 'POST',
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            return response.text().then(text => {
                throw new Error(`Network response was not ok: ${response.status} ${response.statusText}\n${text}`);
            });
        }
        return response.json();
    })
    .then(data => {
        console.log('Analysis complete:', data);
        // Hide processing animation
        document.getElementById('processingAnimation').style.display = 'none';
        // Update the UI with the results
        updateAnalysisResults(data);
    })
    .catch(error => {
        console.error('Error during analysis:', error);
        // Hide processing animation
        document.getElementById('processingAnimation').style.display = 'none';
        alert('An error occurred during analysis. Please try again.');
    });
}

function updateAnalysisResults(data) {
    document.getElementById('treeCount').textContent = data.tree_count;
    document.getElementById('areaCovered').textContent = data.area;
    document.getElementById('treeDensity').textContent = data.density;
    document.getElementById('imageResolution').textContent = data.resolution;

    // Update the chart
    updateChart(data);

    // Display the processed image
    var img = document.getElementById('uploadedImage');
    img.src = '/images/' + data.image_path;
    img.style.display = 'block';

    // Setup download button
    var downloadButton = document.getElementById('downloadProcessedImage');
    downloadButton.style.display = 'block';
    downloadButton.onclick = function() {
        window.location.href = '/download_image/' + data.image_path;
    };
}

function updateChart(data) {
    var ctx = document.getElementById('treeChart').getContext('2d');
    if (window.treeChart instanceof Chart) {
        window.treeChart.destroy();
    }
    window.treeChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: ['Trees Detected', 'Area Covered (km²)', 'Tree Density (per km²)'],
            datasets: [{
                label: 'Tree Analysis Metrics',
                data: [
                    data.tree_count,
                    parseFloat(data.area.split(' ')[0]),
                    parseFloat(data.density.split(' ')[0])
                ],
                backgroundColor: [
                    'rgba(54, 162, 235, 0.6)',
                    'rgba(75, 192, 192, 0.6)',
                    'rgba(255, 206, 86, 0.6)'
                ],
                borderColor: [
                    'rgba(54, 162, 235, 1)',
                    'rgba(75, 192, 192, 1)',
                    'rgba(255, 206, 86, 1)'
                ],
                borderWidth: 1
            }]
        },
        options: {
            scales: {
                y: {
                    beginAtZero: true
                }
            }
        }
    });
}

function setupEventListeners() {
    // Handle form submission for image upload
    var uploadForm = document.getElementById('uploadForm');
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            e.preventDefault();
            const imageFile = document.getElementById('imageUpload').files[0];
            const confidenceThreshold = document.getElementById('confidenceThreshold').value;
            if (imageFile) {
                analyzeTreeImage(imageFile, confidenceThreshold);
            } else {
                alert('Please select an image to analyze.');
            }
        });
    } else {
        console.error('Upload form not found');
    }

    // Handle analysis update for map area
    var updateAnalysisButton = document.getElementById('updateAnalysis');
    if (updateAnalysisButton) {
        updateAnalysisButton.addEventListener('click', function() {
            const confidenceThreshold = document.getElementById('confidenceThreshold').value;
            const selectedArea = document.getElementById('areaInfo').dataset.coordinates;
            if (selectedArea) {
                analyzeTreeImage(null, confidenceThreshold, selectedArea);
            } else {
                alert('Please select an area on the map before updating the analysis.');
            }
        });
    } else {
        console.error('Update analysis button not found');
    }

    // Update confidence threshold display
    var confidenceThreshold = document.getElementById('confidenceThreshold');
    if (confidenceThreshold) {
        confidenceThreshold.addEventListener('input', function(e) {
            var confidenceValue = document.getElementById('confidenceValue');
            if (confidenceValue) {
                confidenceValue.textContent = e.target.value;
            }
        });
    } else {
        console.error('Confidence threshold input not found');
    }
}
