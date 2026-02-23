import os
import json
import socket
import tempfile
import argparse

from flask import Flask, request, render_template, jsonify, redirect, url_for
from urllib.parse import unquote
from app.database import Database

app = Flask(__name__, template_folder=os.path.join('app','templates'), static_folder=os.path.join('app','static'))

# Parse command line arguments
parser = argparse.ArgumentParser()
parser.add_argument('--ipc-path', type=str, default=os.path.join(tempfile.gettempdir(), 'mpv_socket'))
parser.add_argument('--host', type=str, default='127.0.0.1')
parser.add_argument('--port', type=int, default=5000)

args = parser.parse_args()

ipc_path = args.ipc_path

@app.route('/')
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
        "repeat": btn_repeat_state
    }

    return render_template('index.html', btn_states=btn_states)

@app.route('/playing', methods=['POST'])
def playing():
    global ipc_path

    url = request.form['url']
    command = { "command": ["loadfile", url] }

    send_mpv_command(ipc_path, command)

    return jsonify({"status": "success", "url": url})

@app.route('/control/<action>', methods=['POST'])
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

    elif action == 'repeat':
        command = { "command": ["cycle-values", "loop-playlist", "inf", "no"] }

    send_mpv_command(ipc_path, command)
    return jsonify({'message': f'Action {action} executed'})

@app.route('/bookmark', methods=['GET'])
def bookmark():
    db = Database()
    data = db.get_bookmarks()
    return render_template('bookmark/bookmark.html', data=data)

@app.route('/bookmark/add', methods=['GET', 'POST'])
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
def delete_bookmark(bookmark_id):
    try:
        db = Database()
        db.delete_bookmark(bookmark_id)
        return jsonify({"status": "success", "message": "Bookmark deleted successfully"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    return redirect(url_for('bookmark'))

@app.route('/bookmark/edit/<int:bookmark_id>', methods=['GET', 'POST'])
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
def radio():
    db = Database()
    data = db.get_radios()
    return render_template('radio/radio.html', data=data)

@app.route('/radio/add', methods=['GET', 'POST'])
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
def delete_radio(radio_id):
    try:
        db = Database()
        db.delete_radio(radio_id)
        return jsonify({"status": "success", "message": "Radio deleted successfully"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    return redirect(url_for('radio'))

@app.route('/radio/edit/<int:radio_id>', methods=['GET', 'POST'])
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
def get_playlist():
    global ipc_path

    command = { "command": ["get_property", "playlist"] }
    response = send_mpv_command(ipc_path, command)

    return jsonify(json.loads(response)['data'])

@app.route('/playlist/play/<int:index>', methods=['POST'])
def play_item_from_playlist(index):
    global ipc_path

    command = { "command": ["playlist-play-index", str(index)] }
    response = send_mpv_command(ipc_path, command)

    return jsonify(json.loads(response)['error'])

@app.route('/playlist/delete/<int:index>', methods=['POST'])
def delete_item_from_playlist(index):
    global ipc_path

    command = { "command": ["playlist-remove", str(index)] }
    response = send_mpv_command(ipc_path, command)

    return jsonify(json.loads(response)['error'])

@app.route('/media-info')
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

    # Check if media is playing (core-idle is false when playing)
    if (json.loads(playing_response)['data'] == False):
        is_playing = json.loads(playing_response)['data'] == False
        title = json.loads(title_response)['data']
        metadata = json.loads(metadata_response)['data']['Uploader'] if 'Uploader' in json.loads(metadata_response)['data'] else ''
        if ' - Topic' in metadata:
            metadata = metadata.replace(' - Topic', '').strip()

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

if __name__ == '__main__':
    args = parser.parse_args()
    database = Database()
    database.init_db()
    app.register_error_handler(404, page_not_found)
    app.run(host=args.host, port=args.port)
