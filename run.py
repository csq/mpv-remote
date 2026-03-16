import os
import sys
import json
import socket
import tempfile
import argparse

from flask import Flask, request, render_template, jsonify, redirect, url_for, session
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from urllib.parse import unquote
from functools import wraps
from app.database import Database

app = Flask(__name__, template_folder=os.path.join('app','templates'), static_folder=os.path.join('app','static'))
app.secret_key = os.urandom(24)

# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument('--ipc-path', type=str, default=os.path.join(tempfile.gettempdir(), 'mpv_socket'), help='Path to MPV socket (default: /tmp/mpv_socket)')
parser.add_argument('--host', type=str, default='127.0.0.1', help='Host to bind to (default: 127.0.0.1)')
parser.add_argument('--port', type=int, default=5000, help='Port to run the server on (default: 5000)')
parser.add_argument('--auth', type=str, default=None, help='Initialize user credentials (format: username:password)')
parser.add_argument('--allow-upload', action='store_true', help='Allow file upload (default: False)')

args = parser.parse_args()

ipc_path = args.ipc_path

UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), 'mpv-remote', 'uploads')
ALLOWED_EXTENSIONS = {'mp3', 'wma', 'flac', 'wav', 'ogg', 'aac', 'ape', 'alac', 'aiff'}

# Check if authentication is enabled
def auth_enabled():
    return '--auth' in sys.argv

# Check if user is logged in
def is_logged_in():
    return 'username' in session

# Login required decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if auth_enabled() and is_logged_in() == False:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def require_auth_flag(f):
    if auth_enabled():
        return app.route('/login', methods=['GET', 'POST'])(f)
    return f

def required_upload_flag(f):
    if '--allow-upload' in sys.argv:
        return app.route('/upload', methods=['POST'])(f)
    return f

@require_auth_flag
def login():
    if request.method == 'GET':
        if auth_enabled() and is_logged_in():
            return redirect(url_for('index'))
        return render_template('login.html')

    if auth_enabled():
        username, password = args.auth.split(':')

    user_credentials = {
        username: generate_password_hash(password)
    }

    username_input = request.form.get('username')
    password_input = request.form.get('password')

    if username_input == username and check_password_hash(
        user_credentials[username_input], password_input
    ):
        session['username'] = username_input
        return redirect(url_for('index'))

    return render_template('login.html', error='Invalid username or password')

@app.route('/', methods=['GET'])
@login_required
def index():
    global ipc_path

    # states False = unpaused, True = paused
    cmd_state = { "command": ["get_property", "pause"] }
    response = send_mpv_command(ipc_path, cmd_state)
    btn_pause_state = json.loads(response)['data']

    # states False = unmuted, True = muted
    cmd_state = { "command": ["get_property", "mute"] }
    response = send_mpv_command(ipc_path, cmd_state)
    btn_mute_state = json.loads(response)['data']

    # states False = no repeat, inf = repeat
    cmd_state = { "command": ["get_property", "loop-playlist"] }
    response = send_mpv_command(ipc_path, cmd_state)
    btn_repeat_state = json.loads(response)['data']

    btn_states = {
        "pause": btn_pause_state,
        "mute": btn_mute_state,
        "repeat": btn_repeat_state,
        "upload_allowed": False
    }

    # Set upload state based on CLI flag
    btn_states['upload_allowed'] = '--allow-upload' in sys.argv

    return render_template('index.html', btn_states=btn_states)

@app.route('/playing', methods=['POST'])
@login_required
def playing():
    global ipc_path

    url = request.form['url']
    command = { "command": ["loadfile", url] }

    send_mpv_command(ipc_path, command)

    return jsonify({"status": "success", "url": url})

@required_upload_flag
@login_required
def upload_file():
    global ipc_path

    # Create tmp folder if it doesn't exist
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)

    # Get the files from the request
    files = request.files.getlist("file")

    list_paths = []

    # Save the files to the tmp folder
    for file in files:
        if allowed_file_extension(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            list_paths.append(file_path)
            file.save(file_path)

    # Stop current song
    command = { "command": ["stop"] }
    send_mpv_command(ipc_path, command)

    # Load the files
    for path in list_paths:
        command = { "command": ["loadfile", path, "append-play"] }
        send_mpv_command(ipc_path, command)

    return redirect(url_for('index'))

@app.route('/control/<action>', methods=['POST'])
@login_required
def control(action):
    global ipc_path

    if action == 'pause':
        command = { "command": ["cycle", "pause"] }

    elif action == 'next':
        command = { "command": ["playlist_next"] }
    elif action == 'previous':
        command = { "command": ["playlist_prev"] }

    elif action == 'vol_plus':
        current_volume = get_volume()
        new_volume = min(current_volume + 5, 100)
        command = { "command": ["set_property", "volume", str(new_volume)] }
    elif action == 'vol_minus':
        current_volume = get_volume()
        new_volume = max(current_volume - 5, 0)
        command = { "command": ["set_property", "volume", str(new_volume)] }

    elif action == 'mute':
        command = { "command": ["cycle", "mute"] }

    elif action == 'stop':
        command = { "command": ["stop"] }
        clean_tmp_folder()

    elif action == 'repeat':
        command = { "command": ["cycle-values", "loop-playlist", "inf", "no"] }

    send_mpv_command(ipc_path, command)
    return jsonify({'message': f'Action {action} executed'})

@app.route('/bookmark', methods=['GET'])
@login_required
def bookmark():
    db = Database()
    data = db.get_bookmarks()
    return render_template('bookmark/bookmark.html', data=data)

@app.route('/bookmark/add', methods=['GET', 'POST'])
@login_required
def go_to_add_bookmark():
    if request.method == 'GET':
        return render_template('/bookmark/bookmark_form.html', edit_mode=False)
    elif request.method == 'POST':
        db = Database()
        bookmark_name = request.form['name']
        bookmark_url = request.form['url']
        db.insert_bookmark(bookmark_name, bookmark_url)
        return redirect(url_for('bookmark'))

@app.route('/bookmark/delete/<int:bookmark_id>', methods=['POST'])
@login_required
def delete_bookmark(bookmark_id):
    try:
        db = Database()
        db.delete_bookmark(bookmark_id)
        return jsonify({"status": "success", "message": "Bookmark deleted successfully"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    return redirect(url_for('bookmark'))

@app.route('/bookmark/edit/<int:bookmark_id>', methods=['GET', 'POST'])
@login_required
def edit_bookmark(bookmark_id):
    if request.method == 'GET':
        db = Database()
        bookmark = db.get_bookmark_by_id(bookmark_id)
        return render_template('bookmark/bookmark_form.html', edit_mode=True, bookmark=bookmark)
    elif request.method == 'POST':
        db = Database()
        bookmark_id = int(request.form['bookmark_id'])
        new_name = request.form['name']
        new_url = request.form['url']
        db.update_bookmark(bookmark_id, new_name, new_url)
        return redirect(url_for('bookmark'))

@app.route('/bookmark/play/<path:url>', methods=['POST'])
@login_required
def play_bookmark(url):
    global ipc_path

    try:
        decoded_url = unquote(url)
        command = {"command": ["loadfile", decoded_url]}

        # Check if socket exists before sending command
        if not os.path.exists(ipc_path):
            return jsonify({"status": "error", "message": "MPV socket not found"}), 500

        send_mpv_command(ipc_path, command)
        return jsonify({"status": "success", "url": decoded_url})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/radio', methods=['GET'])
@login_required
def radio():
    db = Database()
    data = db.get_radios()
    return render_template('radio/radio.html', data=data)

@app.route('/radio/add', methods=['GET', 'POST'])
@login_required
def go_to_add_radio():
    if request.method == 'GET':
        return render_template('radio/radio_form.html', edit_mode=False)
    elif request.method == 'POST':
        db = Database()
        radio_name = request.form['name']
        radio_url = request.form['url']
        db.insert_radio(radio_name, radio_url)
        return redirect(url_for('radio'))

@app.route('/radio/delete/<int:radio_id>', methods=['POST'])
@login_required
def delete_radio(radio_id):
    try:
        db = Database()
        db.delete_radio(radio_id)
        return jsonify({"status": "success", "message": "Radio deleted successfully"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    return redirect(url_for('radio'))

@app.route('/radio/edit/<int:radio_id>', methods=['GET', 'POST'])
@login_required
def edit_radio(radio_id):
    if request.method == 'GET':
        db = Database()
        radio = db.get_radio_by_id(radio_id)
        return render_template('radio/radio_form.html', edit_mode=True, radio=radio)
    elif request.method == 'POST':
        db = Database()
        radio_id = int(request.form['radio_id'])
        new_name = request.form['name']
        new_url = request.form['url']
        db.update_radio(radio_id, new_name, new_url)
        return redirect(url_for('radio'))

@app.route('/radio/play/<path:url>', methods=['POST'])
@login_required
def play_radio(url):
    global ipc_path

    try:
        decoded_url = unquote(url)
        command = {"command": ["loadfile", decoded_url]}

        # Check if socket exists before sending command
        if not os.path.exists(ipc_path):
            return jsonify({"status": "error", "message": "MPV socket not found"}), 500

        send_mpv_command(ipc_path, command)
        return jsonify({"status": "success", "url": decoded_url})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/playlist', methods=['GET'])
@login_required
def get_playlist():
    global ipc_path

    command = { "command": ["get_property", "playlist"] }
    response = send_mpv_command(ipc_path, command)

    return jsonify(json.loads(response)['data'])

@app.route('/playlist/play/<int:index>', methods=['POST'])
@login_required
def play_item_from_playlist(index):
    global ipc_path

    command = { "command": ["playlist-play-index", str(index)] }
    response = send_mpv_command(ipc_path, command)

    return jsonify(json.loads(response)['error'])

@app.route('/playlist/delete/<int:index>', methods=['POST'])
@login_required
def delete_item_from_playlist(index):
    global ipc_path

    command = { "command": ["playlist-remove", str(index)] }
    response = send_mpv_command(ipc_path, command)

    return jsonify(json.loads(response)['error'])

@app.route('/media-info')
@login_required
def get_media_info():
    global ipc_path

    # Command to check if media is playing
    playing_command = {"command": ["get_property", "core-idle"]}
    playing_response = send_mpv_command(ipc_path, playing_command)

    # Command to get media title
    title_command = {"command": ["get_property", "media-title"]}
    title_response = send_mpv_command(ipc_path, title_command)

    # Command to get metadata
    metadata_command = {"command": ["get_property", "filtered-metadata"]}
    metadata_response = send_mpv_command(ipc_path, metadata_command)

    # Command to get filtered metadata
    filtered_metadata_command = {"command": ["get_property", "filtered-metadata"]}
    filtered_metadata_response = send_mpv_command(ipc_path, filtered_metadata_command)

    # Check if media is playing (core-idle is false when playing)
    if (json.loads(playing_response)['data'] == False):
        is_playing = json.loads(playing_response)['data'] == False
        title = json.loads(title_response)['data']
        metadata = json.loads(metadata_response)['data']['Uploader'] if 'Uploader' in json.loads(metadata_response)['data'] else ''
        if ' - Topic' in metadata:
            metadata = metadata.replace(' - Topic', '').strip()

        artist = json.loads(filtered_metadata_response)['data']['Artist'] if 'Artist' in json.loads(filtered_metadata_response)['data'] else ''
        if metadata == '' and artist != '':
            metadata = artist

        return jsonify({
            'is_playing': is_playing,
            'title': title,
            'metadata': metadata
        })

    return jsonify({
        "is_playing": False,
        "title": None
    })

def page_not_found(error):
    if auth_enabled() and is_logged_in() == False:
        return redirect(url_for('login'))
    return redirect(url_for('index'))

def send_mpv_command(ipc_path, command):
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.connect(ipc_path)

            json_command = json.dumps(command) + '\n'
            sock.sendall(json_command.encode('utf-8'))

            response = sock.recv(4096).decode('utf-8')
            return response
    except (socket.error, IOError) as e:
        print(f"Error sending command to MPV: {e}")
        raise

def get_volume():
    command = { "command": ["get_property", "volume"] }
    response = send_mpv_command(ipc_path, command)
    return json.loads(response)['data']

def allowed_file_extension(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def clean_tmp_folder():
    try:
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)

            if os.path.isfile(file_path) or os.path.islink(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)

    except Exception as e:
        print('Failed to delete tmp folder: ' + str(e))

if __name__ == '__main__':
    args = parser.parse_args()
    database = Database()
    database.init_db()
    app.register_error_handler(404, page_not_found)
    app.run(host=args.host, port=args.port)
