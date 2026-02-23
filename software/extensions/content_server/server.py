"""
Dissertation Video Server - Flask backend for hosting experiment videos
"""

import os
import json
import subprocess
import atexit
from flask import Flask, jsonify, send_from_directory, request

app = Flask(__name__)

# Configuration
BASE_DIR = os.path.dirname(__file__)
VIDEOS_DIR = os.path.join(BASE_DIR, 'videos')
THUMBNAILS_DIR = os.path.join(BASE_DIR, 'thumbnails')
PDFS_DIR = os.path.join(BASE_DIR, 'pdfs')
FIGURES_DIR = os.path.join(BASE_DIR, 'figures')
CODE_DIR = os.path.join(BASE_DIR, 'code')
EXPERIMENTS_FILE = os.path.join(BASE_DIR, 'experiments.json')
SETTINGS_FILE = os.path.join(BASE_DIR, 'settings.json')
FRONTEND_DIR = os.path.join(BASE_DIR, 'frontend')

# Ensure directories exist
os.makedirs(VIDEOS_DIR, exist_ok=True)
os.makedirs(THUMBNAILS_DIR, exist_ok=True)
os.makedirs(PDFS_DIR, exist_ok=True)
os.makedirs(FIGURES_DIR, exist_ok=True)
os.makedirs(CODE_DIR, exist_ok=True)

# Vite process reference
vite_process = None


def start_vite_dev_server(port=9300, host="localhost"):
    """Start the Vite development server"""
    global vite_process

    if not os.path.isdir(FRONTEND_DIR):
        print(f"Frontend directory not found: {FRONTEND_DIR}")
        return None

    if not os.path.isfile(os.path.join(FRONTEND_DIR, "package.json")):
        print(f"No package.json found in: {FRONTEND_DIR}")
        return None

    command = ["npm", "run", "dev", "--", "--port", str(port), "--host", host]

    vite_process = subprocess.Popen(
        command,
        cwd=FRONTEND_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print(f"Vite dev server starting at http://{host}:{port}/ (PID: {vite_process.pid})")
    return vite_process


def stop_vite_dev_server():
    """Stop the Vite development server"""
    global vite_process
    if vite_process:
        vite_process.terminate()
        vite_process.wait()
        print("Vite dev server stopped")


def load_experiments():
    """Load experiments from JSON file"""
    if os.path.exists(EXPERIMENTS_FILE):
        with open(EXPERIMENTS_FILE, 'r') as f:
            return json.load(f)
    return {"folders": [], "experiments": []}


def load_settings():
    """Load settings from JSON file"""
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r') as f:
            return json.load(f)
    return {"title": "Additional Material", "folderStyle": "accordion"}


def find_folder_recursive(folders, folder_id):
    """Recursively find a folder by ID"""
    for folder in folders:
        if folder['id'] == folder_id:
            return folder
        subfolders = folder.get('folders', [])
        if subfolders:
            result = find_folder_recursive(subfolders, folder_id)
            if result:
                return result
    return None


def find_experiment_recursive(data, experiment_id):
    """Recursively find an experiment by ID"""
    def search_folders(folders, parent_path=[]):
        for folder in folders:
            folder_path = parent_path + [{'id': folder['id'], 'name': folder['name']}]
            for exp in folder.get('experiments', []):
                if exp['id'] == experiment_id:
                    return exp, folder_path
            subfolders = folder.get('folders', [])
            if subfolders:
                result = search_folders(subfolders, folder_path)
                if result[0]:
                    return result
        return None, []

    exp, path = search_folders(data.get('folders', []))
    if exp:
        return exp, path

    for exp in data.get('experiments', []):
        if exp['id'] == experiment_id:
            return exp, []

    return None, []


def get_folder_path(data, folder_id):
    """Get the breadcrumb path to a folder"""
    def search(folders, target_id, path=[]):
        for folder in folders:
            current_path = path + [{'id': folder['id'], 'name': folder['name']}]
            if folder['id'] == target_id:
                return current_path
            subfolders = folder.get('folders', [])
            if subfolders:
                result = search(subfolders, target_id, current_path)
                if result:
                    return result
        return None

    return search(data.get('folders', []), folder_id) or []


def count_experiments_recursive(folder):
    """Count all experiments in a folder and its subfolders"""
    count = len(folder.get('experiments', []))
    for subfolder in folder.get('folders', []):
        count += count_experiments_recursive(subfolder)
    return count


@app.route('/api/settings', methods=['GET'])
def get_settings():
    """Get application settings"""
    return jsonify(load_settings())


@app.route('/api/experiments', methods=['GET'])
def get_experiments():
    """Get all experiments and folders"""
    data = load_experiments()
    return jsonify(data)


@app.route('/api/experiments/<experiment_id>', methods=['GET'])
def get_experiment(experiment_id):
    """Get a single experiment by ID"""
    data = load_experiments()
    exp, folder_path = find_experiment_recursive(data, experiment_id)
    if exp:
        result = exp.copy()
        if folder_path:
            result['folderPath'] = folder_path
        return jsonify(result)
    return jsonify({'error': 'Experiment not found'}), 404


@app.route('/api/folders/<folder_id>', methods=['GET'])
def get_folder(folder_id):
    """Get a folder by ID"""
    data = load_experiments()
    folder = find_folder_recursive(data.get('folders', []), folder_id)
    if folder:
        result = folder.copy()
        path = get_folder_path(data, folder_id)
        result['breadcrumb'] = path[:-1] if path else []
        return jsonify(result)
    return jsonify({'error': 'Folder not found'}), 404


@app.route('/api/search', methods=['GET'])
def search_experiments():
    """Search experiments and folders by title/name and description"""
    query = request.args.get('q', '').lower().strip()
    if not query:
        return jsonify({'results': []})

    data = load_experiments()
    results = []

    def search_in_folders(folders, path=[]):
        for folder in folders:
            folder_path = path + [{'id': folder['id'], 'name': folder['name']}]

            # Search folder by name only
            folder_name = folder.get('name', '').lower()
            if query in folder_name:
                results.append({
                    'id': folder['id'],
                    'title': folder['name'],
                    'description': folder['description'],
                    'type': 'folder',
                    'experimentCount': count_experiments_recursive(folder),
                    'folderPath': path  # Parent path, not including self
                })

            # Search experiments in folder by title only
            for exp in folder.get('experiments', []):
                title = exp.get('title', '').lower()
                if query in title:
                    exp_type = exp.get('type', 'synchronized')
                    item_count = len(exp.get('figures', [])) if exp_type == 'figures' else len(exp.get('videos', []))
                    result = {
                        'id': exp['id'],
                        'title': exp['title'],
                        'description': exp['description'],
                        'type': 'experiment',
                        'experimentType': exp_type,
                        'videoCount': item_count,
                        'folderPath': folder_path
                    }
                    if exp_type == 'code':
                        result['language'] = exp.get('language', 'plaintext')
                    results.append(result)

            # Search subfolders
            if folder.get('folders'):
                search_in_folders(folder['folders'], folder_path)

    search_in_folders(data.get('folders', []))

    # Also search root experiments by title only
    for exp in data.get('experiments', []):
        title = exp.get('title', '').lower()
        if query in title:
            exp_type = exp.get('type', 'synchronized')
            item_count = len(exp.get('figures', [])) if exp_type == 'figures' else len(exp.get('videos', []))
            result = {
                'id': exp['id'],
                'title': exp['title'],
                'description': exp['description'],
                'type': 'experiment',
                'experimentType': exp_type,
                'videoCount': item_count,
                'folderPath': []
            }
            if exp_type == 'code':
                result['language'] = exp.get('language', 'plaintext')
            results.append(result)

    return jsonify({'results': results})


@app.route('/videos/<path:filename>')
def serve_video(filename):
    """Serve video files with caching headers"""
    response = send_from_directory(VIDEOS_DIR, filename)
    # Enable browser caching for video files
    response.headers['Cache-Control'] = 'public, max-age=31536000'
    response.headers['Accept-Ranges'] = 'bytes'
    return response


@app.route('/thumbnails/<path:filename>')
def serve_thumbnail(filename):
    """Serve thumbnail images"""
    return send_from_directory(THUMBNAILS_DIR, filename)


@app.route('/pdfs/<path:filename>')
def serve_pdf(filename):
    """Serve PDF files"""
    return send_from_directory(PDFS_DIR, filename)


@app.route('/figures/<path:filename>')
def serve_figure(filename):
    """Serve figure images"""
    return send_from_directory(FIGURES_DIR, filename)


@app.route('/code/<path:filename>')
def serve_code(filename):
    """Serve code files"""
    return send_from_directory(CODE_DIR, filename, mimetype='text/plain')


@app.route('/api/videos', methods=['GET'])
def list_videos():
    """List all available videos in the videos directory"""
    videos = []
    if os.path.exists(VIDEOS_DIR):
        for root, dirs, files in os.walk(VIDEOS_DIR):
            for file in files:
                if file.lower().endswith(('.mp4', '.webm', '.mov', '.avi')):
                    rel_path = os.path.relpath(os.path.join(root, file), VIDEOS_DIR)
                    videos.append(rel_path)
    return jsonify({'videos': videos})


if __name__ == '__main__':
    print(f"Videos directory: {VIDEOS_DIR}")
    print(f"Thumbnails directory: {THUMBNAILS_DIR}")
    print(f"Experiments file: {EXPERIMENTS_FILE}")

    # Start Vite dev server
    start_vite_dev_server(port=9300, host="0.0.0.0")
    atexit.register(stop_vite_dev_server)

    # Start Flask server
    app.run(host='0.0.0.0', port=5050, debug=True, use_reloader=False)
