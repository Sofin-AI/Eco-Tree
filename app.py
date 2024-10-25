import os
import logging
from flask import Flask, render_template, request, jsonify, send_file, url_for, send_from_directory
from PIL import Image
from ultralytics import YOLO
import math
import requests
import io
import csv
from datetime import datetime
import traceback
import numpy as np
import cv2
from flask_talisman import Talisman

app = Flask(__name__, static_folder='static', static_url_path='/static')
Talisman(app, content_security_policy=None)

app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 31536000  # 1 year in seconds
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB limit

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'max-age=31536000, immutable'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.context_processor
def override_url_for():
    return dict(url_for=dated_url_for)

def dated_url_for(endpoint, **values):
    if endpoint == 'static':
        filename = values.get('filename', None)
        if filename:
            file_path = os.path.join(app.root_path, endpoint, filename)
            try:
                values['q'] = int(os.stat(file_path).st_mtime)
            except FileNotFoundError:
                app.logger.warning(f"Static file not found: {file_path}")
                # You could set a default value or just pass without setting 'q'
                pass
    return url_for(endpoint, **values)

# Global variables and setup
output_dir = "C:\\Code\\project\\output"
os.makedirs(output_dir, exist_ok=True)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

logger.info("Setting up model...")
model_path = "C:\\Code\\porject3\\runs\\obb\\tRRE\\weights\\best.pt"
try:
    model = YOLO(model_path)
    logger.info("Model setup completed.")
except Exception as e:
    logger.error(f"Error loading model: {e}")
    model = None

# Download tile
def download_tile(x, y, zoom):
    url = f"https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={zoom}"
    response = requests.get(url)
    if response.status_code == 200:
        return response.content
    else:
        logger.error(f"Failed to download tile. Status code: {response.status_code}")
        logger.error(f"URL: {url}")
        return None

# Process each tile
def process_tile(tile_data, conf):
    try:
        img = Image.open(io.BytesIO(tile_data))
        img_np = np.array(img)
        results = model(img_np, conf=conf)
        
        for result in results:
            img_with_boxes = result.plot(line_width=1, font_size=8)
            
            if hasattr(result, 'boxes') and result.boxes is not None:
                tree_count = len(result.boxes)
            elif hasattr(result, 'obb') and result.obb is not None:
                tree_count = len(result.obb)
            else:
                tree_count = 0
                logger.warning("Unable to find valid 'boxes' or 'obb' attribute")
            
            return Image.fromarray(img_with_boxes), tree_count
    except Exception as e:
        logger.error(f"Error processing tile: {e}")
        return None, 0

# Download and process area
def download_and_process_area(lat1, lon1, lat2, lon2, zoom, conf, iou, max_det):
    x1, y1 = lat_lon_to_tile(lat1, lon1, zoom)
    x2, y2 = lat_lon_to_tile(lat2, lon2, zoom)
    x1, x2 = min(x1, x2), max(x1, x2)
    y1, y2 = min(y1, y2), max(y1, y2)

    width = (x2 - x1 + 1) * 256
    height = (y2 - y1 + 1) * 256
    result_image = Image.new('RGB', (width, height))
    total_trees = 0
    total_tiles = (x2 - x1 + 1) * (y2 - y1 + 1)
    processed_tiles = 0

    for x in range(x1, x2 + 1):
        for y in range(y1, y2 + 1):
            tile_data = download_tile(x, y, zoom)
            if tile_data:
                processed_tile, tree_count = process_tile(tile_data, conf)
                if processed_tile:
                    result_image.paste(processed_tile, ((x - x1) * 256, (y - y1) * 256))
                    total_trees += tree_count
            processed_tiles += 1
            progress = (processed_tiles / total_tiles) * 100

    return result_image, total_trees, 100  # Return 100% progress when done

# Helper function for tile coordinates
def lat_lon_to_tile(lat, lon, zoom):
    x = math.floor((lon + 180) / 360 * (1 << zoom))
    y = math.floor((1 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2 * (1 << zoom))
    return x, y

# Calculate tree density
def calculate_tree_density(tree_count, area_km2):
    if area_km2 == 0:
        return "N/A (area is too small)"
    density = tree_count / area_km2
    return f"{density:.2f} trees per km²"

# Calculate area
def calculate_area(lat1, lon1, lat2, lon2):
    R = 6371  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2) * math.sin(dlat/2) +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon/2) * math.sin(dlon/2))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    area = R * c
    return area * area  # Approximate rectangular area

# Save results
def save_results(lat1, lon1, lat2, lon2, zoom, tree_count):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    results = [timestamp, lat1, lon1, lat2, lon2, zoom, tree_count]
    with open('tree_detection_results.csv', 'a', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(results)

# Index route
@app.route('/')
def index():
    logger.info("Index route called")
    return render_template('index.html')

# Process area route
@app.route('/process_area', methods=['POST'])
def process_area():
    logger.info("Process area route called")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request headers: {request.headers}")
    logger.info(f"Request form data: {request.form}")
    logger.info(f"Request files: {request.files}")
    
    if model is None:
        logger.error("Model is not loaded")
        return jsonify({'error': 'Model is not loaded'}), 500

    try:
        coordinates = request.form.get('coordinates')
        conf = float(request.form.get('conf', 0.5))
        iou = float(request.form.get('iou', 0.5))
        max_det = int(request.form.get('max_det', 300))

        if not coordinates:
            return jsonify({'error': 'No coordinates provided'}), 400

        coordinates = [float(coord) for coord in coordinates.split(',')]
        lat1, lon1, lat2, lon2 = coordinates

        zoom = 18  # You may want to make this configurable
        
        # Calculate approximate resolution in meters per pixel
        lat_center = (lat1 + lat2) / 2
        resolution_meters = 156543.03392 * math.cos(math.radians(lat_center)) / (2 ** zoom)

        logger.info(f"Processing area: lat1={lat1}, lon1={lon1}, lat2={lat2}, lon2={lon2}, zoom={zoom}")

        result_image, tree_count, progress = download_and_process_area(lat1, lon1, lat2, lon2, zoom, conf, iou, max_det)
        
        if result_image is None:
            logger.error("Failed to process area")
            return jsonify({'error': 'Failed to process area'}), 500

        # Save the image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"processed_area_{timestamp}.jpg"
        image_path = os.path.join(output_dir, image_filename)
        result_image.save(image_path)

        # Get image dimensions
        image_width, image_height = result_image.size

        # Calculate area and density
        area_km2 = calculate_area(lat1, lon1, lat2, lon2)  # Call the function here
        density = calculate_tree_density(tree_count, area_km2)

        # Save results to CSV
        save_results(lat1, lon1, lat2, lon2, zoom, tree_count)

        response_data = {
            'tree_count': tree_count,
            'area': f"{area_km2:.2f} km²",
            'density': density,
            'resolution': f"{image_width}x{image_height}",
            'image_path': image_filename,
            'progress': progress,
            'debug_info': {
                'lat1': lat1, 'lon1': lon1, 'lat2': lat2, 'lon2': lon2,
                'zoom': zoom, 'conf': conf, 'iou': iou, 'max_det': max_det
            }
        }

        logger.info(f"Sending response: {response_data}")
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error processing area: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

# Serve image route
@app.route('/images/<filename>')
def serve_image(filename):
    try:
        return send_file(os.path.join(output_dir, filename), mimetype='image/jpeg')
    except FileNotFoundError:
        logger.error(f"Image file not found: {filename}")
        return jsonify({'error': 'Image not found'}), 404

# Download image route
@app.route('/download_image/<path:filename>')
def download_image(filename):
    return send_file(os.path.join(output_dir, filename), as_attachment=True)

@app.route('/test', methods=['GET'])
def test():
    return jsonify({'message': 'Test successful'})

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory(app.static_folder, filename)

@app.route('/process_image', methods=['POST'])
def process_image():
    logger.info("Process image route called")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request headers: {request.headers}")
    logger.info(f"Request form data: {request.form}")
    logger.info(f"Request files: {request.files}")
    
    if model is None:
        logger.error("Model is not loaded")
        return jsonify({'error': 'Model is not loaded'}), 500

    try:
        if 'image' not in request.files:
            logger.error("No image file in request")
            return jsonify({'error': 'No image file provided'}), 400
        
        image_file = request.files['image']
        conf = float(request.form.get('conf', 0.5))
        
        # Process the image
        img = Image.open(image_file)
        img_np = np.array(img)
        results = model(img_np, conf=conf)
        
        # Process results
        for result in results:
            img_with_boxes = result.plot(line_width=1, font_size=8)
            
            if hasattr(result, 'boxes') and result.boxes is not None:
                tree_count = len(result.boxes)
            elif hasattr(result, 'obb') and result.obb is not None:
                tree_count = len(result.obb)
            else:
                tree_count = 0
                logger.warning("Unable to find valid 'boxes' or 'obb' attribute")
        
        # Save the processed image
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_filename = f"processed_image_{timestamp}.jpg"
        image_path = os.path.join(output_dir, image_filename)
        Image.fromarray(img_with_boxes).save(image_path)

        # Get image dimensions
        image_width, image_height = img.size

        response_data = {
            'tree_count': tree_count,
            'area': "N/A (single image)",
            'density': "N/A (single image)",
            'resolution': f"{image_width}x{image_height}",
            'image_path': image_filename,
            'progress': 100,
        }

        logger.info(f"Sending response: {response_data}")
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error processing image: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

@app.route('/update_analysis', methods=['POST'])
def update_analysis():
    logger.info("Update analysis route called")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request headers: {request.headers}")
    logger.info(f"Request form data: {request.form}")
    
    if model is None:
        logger.error("Model is not loaded")
        return jsonify({'error': 'Model is not loaded'}), 500

    try:
        conf = float(request.form.get('conf', 0.5))
        coordinates = request.form.get('coordinates')
        
        # Here, you would typically retrieve the last processed image
        # and re-run the analysis with the new confidence threshold
        # For this example, we'll just return dummy data
        
        # Check if the last processed image exists
        last_image_path = "last_processed_image.jpg"
        full_image_path = os.path.join(output_dir, last_image_path)
        
        if os.path.exists(full_image_path):
            image_path = last_image_path
        else:
            image_path = ""

        response_data = {
            'tree_count': 100,  # Example value
            'area': "5.0 km²",  # Example value
            'density': "20 trees per km²",  # Example value
            'resolution': "1000x1000",  # Example value
            'image_path': image_path,
            'progress': 100,
        }

        logger.info(f"Sending response: {response_data}")
        return jsonify(response_data)

    except Exception as e:
        logger.error(f"Error updating analysis: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500

if __name__ == '__main__':
    print("Starting the application")
    logger.info("Starting the application")
    app.run(debug=True)
