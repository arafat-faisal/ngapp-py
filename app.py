import sys
import json
import os
import re
import urllib.parse
import requests
import subprocess
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS # Required for cross-origin requests from frontend
from datetime import datetime # Import datetime here

# --- Configuration ---
# Directory to save downloaded images and videos
DOWNLOAD_DIR = "downloads"
# File to store archived Storyblocks links
STORYBLOCKS_ARCHIVE_FILE = "storyblocks_links.json"
# File to save the transcription with frame durations
TRANSCRIPTION_FRAMES_FILE = "transcription_frames.json"
# File to save the video composition data
COMPOSITION_JSON_FILE = "composition.json"
# File to track downloaded images by their original URL
IMAGE_DOWNLOADS_FILE = "image_downloads.json"

# Input JSON and CSV file paths (relative to script location)
# These files are expected to be in the same directory as app.py
TRANSCRIPTION_JSON_PATH = "transcription.json"
SEARCH_TERMS_JSON_PATH = "search_terms.json"

# Ensure download directory exists
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__)
CORS(app) # Enable CORS for all routes

# --- Global Data Stores (Loaded on startup) ---
transcription_data = {}
search_terms_data = {}
image_downloads_data = {}
composition_data = {}
video_fps = None # Global variable to store FPS

# --- Helper Functions (Adapted from original script) ---

def load_json_file(file_path, default_data=None):
    """Loads and parses a JSON file, returning default_data if not found or invalid."""
    try:
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            print(f"Warning: File not found: {file_path}. Returning default data.")
            return default_data if default_data is not None else {}
    except json.JSONDecodeError:
        print(f"Error decoding JSON from {file_path}. Returning default data.")
        return default_data if default_data is not None else {}
    except Exception as e:
        print(f"An unexpected error occurred loading {file_path}: {e}. Returning default data.")
        return default_data if default_data is not None else {}

def save_json_file(file_path, data):
    """Saves data to a JSON file."""
    try:
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"Error saving JSON to {file_path}: {e}")
        return False

def load_transcription_data_web(file_path):
    """Loads and parses the transcription JSON file for web app."""
    data = load_json_file(file_path)
    if 'segments' in data:
        indexed_data = {}
        for i, segment in enumerate(data['segments']):
            segment_id = str(segment.get('id', i))
            indexed_data[segment_id] = {
                "sentence": segment.get('text', ''),
                "start_seconds": segment.get('start', 0.0),
                "end_seconds": segment.get('end', 0.0),
                "duration_seconds": segment.get('end', 0.0) - segment.get('start', 0.0)
            }
        return indexed_data
    else:
        print(f"Invalid transcription JSON format. Missing 'segments' key in {file_path}")
        return {}

def load_search_terms_data_web(file_path):
    """Loads and parses the search terms JSON file for web app."""
    data = load_json_file(file_path)
    search_terms_dict = {}
    for key, info in data.items():
        youtube_terms = info.get('Youtube Search Terms', [])
        if isinstance(youtube_terms, str):
            youtube_terms = [t.strip() for t in youtube_terms.split(',') if t.strip()]
        
        search_engine_terms = info.get('Search Engine Search terms', [])
        if isinstance(search_engine_terms, str):
            search_engine_terms = [t.strip() for t in search_engine_terms.split(',') if t.strip()]
        
        movie_suggestion = info.get('Movie Suggestion', [])
        if isinstance(movie_suggestion, str):
            movie_suggestion = [t.strip() for t in movie_suggestion.split(',') if t.strip()]

        search_terms_dict[key] = {
            "sentence": info.get('sentence', ''),
            "Youtube Search Terms": youtube_terms,
            "Search Engine Search terms": search_engine_terms,
            "Movie Suggestion": movie_suggestion
        }
    return search_terms_dict

def get_initial_composition_data():
    """Provides the default structure for composition data."""
    return {
        "sequence": {
            "name": "New Video Composition",
            "timebase": 30, # Default timebase, can be updated by FPS selection
            "ntsc": False,
            "width": 1920,
            "height": 1080,
            "clips": []
        }
    }

def _get_next_available_track(linked_transcript_index, current_composition_data):
    """
    Determines the next available track number for a given linked_transcript_index.
    It finds the maximum track number currently used by any clip associated with that index
    and returns max_track + 1. If no clips are found for the index, it returns 0.
    """
    max_track_for_index = -1
    if "sequence" in current_composition_data and "clips" in current_composition_data["sequence"]:
        for clip in current_composition_data["sequence"]["clips"]:
            if clip.get('linked_transcript_index') == linked_transcript_index:
                max_track_for_index = max(max_track_for_index, clip.get('track', -1))
    return max_track_for_index + 1

def update_composition_json_data(clip_entry):
    """Adds a new clip entry to the composition JSON data, assigning it to the next available track."""
    global composition_data # Modify the global composition_data

    # Ensure 'sequence' key exists and has the correct structure
    if "sequence" not in composition_data:
        composition_data["sequence"] = get_initial_composition_data()["sequence"]
    
    # Ensure 'clips' is a list
    if "clips" not in composition_data["sequence"] or not isinstance(composition_data["sequence"]["clips"], list):
        composition_data["sequence"]["clips"] = []

    # Determine the next available track for this linked_transcript_index
    linked_idx = clip_entry.get('linked_transcript_index')
    if linked_idx is not None:
        new_track = _get_next_available_track(linked_idx, composition_data)
        clip_entry['track'] = new_track
    else:
        # Fallback if linked_transcript_index is missing, assign a default track (e.g., 0)
        clip_entry['track'] = 0 

    composition_data["sequence"]["clips"].append(clip_entry)
    return save_json_file(COMPOSITION_JSON_FILE, composition_data)

def is_image_url(url):
    """
    Checks if a URL is likely an image by checking extension and content-type header.
    """
    image_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.webp']
    parsed_url = urllib.parse.urlparse(url)
    path = parsed_url.path.lower()

    # Check by extension first (quick check)
    if any(path.endswith(ext) for ext in image_extensions):
        return True
    
    # More robust check using HTTP HEAD request
    try:
        response = requests.head(url, timeout=5)
        if 'Content-Type' in response.headers and response.headers['Content-Type'].startswith('image/'):
            return True
    except requests.exceptions.RequestException:
        pass # Ignore network errors during HEAD request
    return False

# --- Initialize data on Flask app start ---
@app.before_first_request
def initialize_data():
    global transcription_data, search_terms_data, image_downloads_data, composition_data, video_fps
    transcription_data = load_transcription_data_web(TRANSCRIPTION_JSON_PATH)
    search_terms_data = load_search_terms_data_web(SEARCH_TERMS_JSON_PATH)
    image_downloads_data = load_json_file(IMAGE_DOWNLOADS_FILE, {})
    composition_data = load_json_file(COMPOSITION_JSON_FILE, get_initial_composition_data())
    video_fps = composition_data.get("sequence", {}).get("timebase", None)


# --- API Endpoints ---

@app.route('/api/data/<int:index>', methods=['GET'])
def get_data_for_index(index):
    """Returns transcription and search terms data for a given index."""
    global transcription_data, search_terms_data, video_fps

    current_key = str(index)
    segment_data = transcription_data.get(current_key, {})
    search_data = search_terms_data.get(current_key, {})

    if not segment_data:
        return jsonify({"error": "Index out of bounds or no data for this index"}), 404

    response_data = {
        "index": index,
        "max_index": len(transcription_data) - 1,
        "sentence": segment_data.get("sentence", "N/A"),
        "start_seconds": segment_data.get("start_seconds", 0.0),
        "end_seconds": segment_data.get("end_seconds", 0.0),
        "duration_seconds": segment_data.get("duration_seconds", 0.0),
        "youtube_terms": search_data.get("Youtube Search Terms", []),
        "search_engine_terms": search_data.get("Search Engine Search terms", []),
        "movie_suggestion": search_data.get("Movie Suggestion", []),
        "video_fps": video_fps
    }
    return jsonify(response_data)

@app.route('/api/process_url', methods=['POST'])
def process_url():
    """Identifies URL type and triggers appropriate action."""
    data = request.get_json()
    url = data.get('url')
    current_index = str(data.get('currentIndex'))

    if not url:
        return jsonify({"status": "error", "message": "URL not provided"}), 400

    parsed_url = urllib.parse.urlparse(url)
    domain = parsed_url.netloc.lower()

    if "youtube.com" in domain or "youtu.be" in domain:
        # For YouTube, we'll return metadata and let the frontend confirm
        # The actual download will happen in a separate endpoint after confirmation
        return jsonify({"status": "youtube_metadata_request", "url": url})
    elif "storyblocks.com" in domain or "a.storyblok.com" in domain:
        return archive_storyblocks_link(url, current_index)
    elif is_image_url(url):
        return download_image_api(url, current_index)
    else:
        return jsonify({"status": "error", "message": f"Unsupported link type: {url}"}), 400

@app.route('/api/fetch_youtube_metadata', methods=['POST'])
def fetch_youtube_metadata_api():
    """Fetches YouTube video metadata using yt-dlp."""
    data = request.get_json()
    url = data.get('url')

    ydl_opts = {
        'quiet': True,
        'skip_download': True,
        'forcejson': True,
        'extract_flat': False,
    }

    try:
        # Using subprocess.run for simplicity, but for long-running tasks
        # in a production Flask app, you'd use a task queue (e.g., Celery).
        process = subprocess.run([sys.executable, '-m', 'yt_dlp', '--dump-json', '--', url], 
                              capture_output=True, text=True, check=True, timeout=30)
            
        info = json.loads(process.stdout)
        metadata = {
            "video_id": info.get("id"),
            "title": info.get("title"),
            "duration_seconds": info.get("duration"),
            "thumbnail_url": info.get("thumbnail"),
            "uploader": info.get("uploader"),
        }
        return jsonify({"status": "success", "metadata": metadata})
    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "message": "YouTube metadata fetch timed out."}), 500
    except subprocess.CalledProcessError as e:
        return jsonify({"status": "error", "message": f"yt-dlp error: {e.stderr.strip()}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to fetch YouTube metadata: {e}"}), 500

@app.route('/api/download_youtube', methods=['POST'])
def download_youtube_api():
    """Triggers YouTube video download via a separate script."""
    data = request.get_json()
    youtube_id = data.get('youtube_id')
    current_index = str(data.get('currentIndex'))
    metadata = data.get('metadata', {}) # Full metadata from frontend
    
    if not youtube_id:
        return jsonify({"status": "error", "message": "YouTube ID not provided"}), 400

    try:
        # Use subprocess to run the external youtube_downloader.py script
        # This script will handle the actual download and save it to DOWNLOAD_DIR
        command = [sys.executable, "youtube_downloader.py", youtube_id, DOWNLOAD_DIR]
        
        # Run the subprocess and wait for its completion
        process = subprocess.run(command, capture_output=True, text=True, check=True)

        if "DOWNLOAD_SUCCESS:" in process.stdout:
            downloaded_file_path = process.stdout.split("DOWNLOAD_SUCCESS:")[1].strip()
            filename = os.path.basename(downloaded_file_path)
            
            # Prepare clip entry for composition
            current_segment = transcription_data.get(current_index, {})
            start_seconds = current_segment.get("start_seconds", 0.0)
            end_seconds = current_segment.get("end_seconds", 0.0)
            
            start_frame = int(round(start_seconds * video_fps)) if video_fps is not None else 0
            end_frame = int(round(end_seconds * video_fps)) if video_fps is not None else 0
            duration_frames = int(round(end_frame - start_frame))

            clip_entry = {
                "filename": filename,
                "start": start_frame,
                "duration": duration_frames,
                "source_url": f"https://www.youtube.com/watch?v={youtube_id}",
                "linked_transcript_index": int(current_index),
                "channel-name": metadata.get("uploader", '')
            }
            update_composition_json_data(clip_entry)
            return jsonify({"status": "success", "message": "YouTube download completed and composition updated.", "filename": filename})
        else:
            return jsonify({"status": "error", "message": f"YouTube download script failed: {process.stderr.strip()}"}), 500

    except subprocess.CalledProcessError as e:
        return jsonify({"status": "error", "message": f"YouTube download failed with error: {e.stderr.strip()}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to initiate YouTube download: {e}"}), 500

@app.route('/api/download_image', methods=['POST'])
def download_image_api(url=None, current_index=None):
    """Downloads an image and updates composition JSON."""
    global image_downloads_data, video_fps, transcription_data

    # Check if parameters are provided via function call (e.g., from process_url)
    # or from request JSON (e.g., direct call from frontend)
    if url is None or current_index is None:
        data = request.get_json()
        url = data.get('url')
        current_index = str(data.get('currentIndex'))

    if not url or not current_index:
        return jsonify({"status": "error", "message": "URL or current index not provided"}), 400

    # Check if image is already downloaded
    if url in image_downloads_data:
        existing_file_path = image_downloads_data[url]
        filename = os.path.basename(existing_file_path)
        current_segment = transcription_data.get(current_index, {})
        start_seconds = current_segment.get("start_seconds", 0.0)
        end_seconds = current_segment.get("end_seconds", 0.0)
        
        # Add to composition even if already downloaded
        _add_image_to_composition(filename, url, start_seconds, end_seconds, int(current_index))
        return jsonify({"status": "success", "message": f"Image already downloaded: {filename}. Added to composition.", "filename": filename})

    current_segment = transcription_data.get(current_index, {})
    sentence = current_segment.get("sentence", "untitled_segment")
    start_seconds = current_segment.get("start_seconds", 0.0)
    end_seconds = current_segment.get("end_seconds", 0.0)

    sanitized_sentence = re.sub(r'[^\w\s-]', '', sentence).strip().replace(' ', '_')
    if len(sanitized_sentence) > 50:
        sanitized_sentence = sanitized_sentence[:50].rstrip('_') + "..."

    original_extension = os.path.splitext(urllib.parse.urlparse(url).path)[1]
    if not original_extension:
        original_extension = ".png"
    
    base_filename = f"{current_index}_{sanitized_sentence}"
    filename = f"{base_filename}{original_extension}"
    file_path = os.path.join(DOWNLOAD_DIR, filename)

    counter = 1
    while os.path.exists(file_path):
        filename = f"{base_filename}_{counter}{original_extension}"
        file_path = os.path.join(DOWNLOAD_DIR, filename)
        counter += 1

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, stream=True, headers=headers, timeout=10)
        response.raise_for_status()

        with open(file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        image_downloads_data[url] = file_path
        save_json_file(IMAGE_DOWNLOADS_FILE, image_downloads_data)
        
        _add_image_to_composition(os.path.basename(file_path), url, start_seconds, end_seconds, int(current_index))

        return jsonify({"status": "success", "message": "Image downloaded and composition updated.", "filename": os.path.basename(file_path)})
    except requests.exceptions.RequestException as e:
        return jsonify({"status": "error", "message": f"Network error downloading image: {e}"}), 500
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error downloading image: {e}"}), 500

def _add_image_to_composition(filename, original_url, start_seconds, end_seconds, linked_transcript_index):
    """Helper to add image details to the composition JSON."""
    global video_fps
    
    start_frame = int(round(start_seconds * video_fps)) if video_fps is not None else 0
    end_frame = int(round(end_seconds * video_fps)) if video_fps is not None else 0
    duration_frames = int(round(end_frame - start_frame))

    image_clip_entry = {
        "filename": filename,
        "start": start_frame,
        "duration": duration_frames,
        "source_url": original_url,
        "linked_transcript_index": linked_transcript_index
    }
    return update_composition_json_data(image_clip_entry)


@app.route('/api/archive_storyblocks', methods=['POST'])
def archive_storyblocks_link(url=None, current_index=None):
    """Archives the Storyblocks link with the current transcription index."""
    # Check if parameters are provided via function call (e.g., from process_url)
    # or from request JSON (e.g., direct call from frontend)
    if url is None or current_index is None:
        data = request.get_json()
        url = data.get('url')
        current_index = str(data.get('currentIndex'))

    if not url or not current_index:
        return jsonify({"status": "error", "message": "URL or current index not provided"}), 400

    archive_data = load_json_file(STORYBLOCKS_ARCHIVE_FILE, {})

    if current_index not in archive_data:
        archive_data[current_index] = []
    archive_data[current_index].append({
        "url": url,
        "timestamp": datetime.now().isoformat()
    })

    if save_json_file(STORYBLOCKS_ARCHIVE_FILE, archive_data):
        return jsonify({"status": "success", "message": f"Storyblocks link archived for index {current_index}."})
    else:
        return jsonify({"status": "error", "message": "Failed to archive Storyblocks link."}), 500

@app.route('/api/set_fps', methods=['POST'])
def set_fps():
    """Sets the video FPS and updates composition data."""
    global video_fps, composition_data
    data = request.get_json()
    fps = data.get('fps')

    if fps is None:
        return jsonify({"status": "error", "message": "FPS not provided"}), 400
    
    try:
        fps = float(fps)
        video_fps = fps
        if "sequence" in composition_data:
            composition_data["sequence"]["timebase"] = int(round(fps))
            save_json_file(COMPOSITION_JSON_FILE, composition_data)
        return jsonify({"status": "success", "message": f"FPS set to {fps:.2f}."})
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid FPS value."}), 400

@app.route('/api/generate_frame_based_json', methods=['POST'])
def generate_frame_based_json_api():
    """Generates a new JSON file with frame durations."""
    global video_fps, transcription_data

    if video_fps is None:
        return jsonify({"status": "error", "message": "Video FPS not set. Please set FPS first."}), 400

    if not transcription_data:
        return jsonify({"status": "error", "message": "No transcription data loaded."}), 400

    frame_based_data = {}
    for key, segment in transcription_data.items():
        new_segment = segment.copy()
        start_seconds = new_segment.get("start_seconds", 0.0)
        end_seconds = new_segment.get("end_seconds", 0.0)
        duration_seconds = new_segment.get("duration_seconds", 0.0)

        new_segment["start_frame"] = int(round(start_seconds * video_fps))
        new_segment["end_frame"] = int(round(end_seconds * video_fps))
        new_segment["duration_frames"] = int(round(duration_seconds * video_fps))
        frame_based_data[key] = new_segment

    frame_based_data["_metadata"] = {"video_fps": video_fps}

    if save_json_file(TRANSCRIPTION_FRAMES_FILE, frame_based_data):
        return jsonify({"status": "success", "message": f"Frame-based transcription saved to {TRANSCRIPTION_FRAMES_FILE}"})
    else:
        return jsonify({"status": "error", "message": "Failed to save frame-based JSON."}), 500

# Route to serve static files (your React build)
@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_static_files(path):
    if path != "" and os.path.exists(app.static_folder + '/' + path):
        return send_from_directory(app.static_folder, path)
    else:
        return send_from_directory(app.static_folder, 'index.html')

# Set the static folder to where your React build output will be
app.static_folder = os.path.abspath('frontend/build')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
