import os
import sqlite3

from platformdirs import user_config_dir

class Database:
    def __init__(self):
        self.db_path = os.path.join(user_config_dir('mpv-remote', 'mpv-remote'), 'db.sqlite3')

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def close_connection(self, connection):
        connection.close()

    def create_table_radio(self):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS radio (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE
            )
        ''')
        connection.commit()
        self.close_connection(connection)

    def get_radio_by_id(self, radio_id):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM radio WHERE id = ?', (radio_id,))
        row = cursor.fetchone()
        self.close_connection(connection)
        return row

    def insert_radio(self, name, url):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('INSERT INTO radio (name, url) VALUES (?, ?)', (name, url))
        connection.commit()
        self.close_connection(connection)

    def get_radios(self):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM radio')
        rows = cursor.fetchall()
        self.close_connection(connection)
        return rows

    def delete_radio(self, radio_id):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('DELETE FROM radio WHERE id = ?', (radio_id,))
        connection.commit()
        self.close_connection(connection)

    def update_radio(self, radio_id, name, url):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('UPDATE radio SET name = ?, url = ? WHERE id = ?', (name, url, radio_id))
        connection.commit()
        self.close_connection(connection)

    def create_table_bookmark(self):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookmark (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE
            )
        ''')
        connection.commit()
        self.close_connection(connection)

    def insert_bookmark(self, name, url):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('INSERT INTO bookmark (name, url) VALUES (?, ?)', (name, url))
        connection.commit()
        self.close_connection(connection)

    def get_bookmarks(self):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM bookmark')
        rows = cursor.fetchall()
        self.close_connection(connection)
        return rows

    def delete_bookmark(self, bookmark_id):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('DELETE FROM bookmark WHERE id = ?', (bookmark_id,))
        connection.commit()
        self.close_connection(connection)

    def update_bookmark(self, bookmark_id, name, url):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('UPDATE bookmark SET name = ?, url = ? WHERE id = ?', (name, url, bookmark_id))
        connection.commit()
        self.close_connection(connection)

    def get_bookmark_by_id(self, bookmark_id):
        connection = self.get_connection()
        cursor = connection.cursor()
        cursor.execute('SELECT * FROM bookmark WHERE id = ?', (bookmark_id,))
        row = cursor.fetchone()
        self.close_connection(connection)
        return row

    def init_db(self):
        try:
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
            open(self.db_path, 'a').close()
        except Exception as e:
            print(e)

        self.create_table_radio()
        self.create_table_bookmark()
