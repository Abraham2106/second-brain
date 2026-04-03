import sqlite3
import json
from datetime import datetime

DB_PATH = "ai_team.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            agent_role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vault_nodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            type TEXT NOT NULL, -- 'file' o 'folder'
            content TEXT, -- Contenido para búsqueda profunda
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vault_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path TEXT NOT NULL,
            target_name TEXT NOT NULL,
            context TEXT,
            FOREIGN KEY (source_path) REFERENCES vault_nodes(path)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vault_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            node_path TEXT NOT NULL,
            tag TEXT NOT NULL,
            FOREIGN KEY (node_path) REFERENCES vault_nodes(path)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS file_edits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            task_id TEXT,
            agent_role TEXT,
            filepath TEXT,
            before_sha256 TEXT,
            after_sha256 TEXT,
            diff_text TEXT,
            status TEXT, -- 'applied', 'conflict', 'skipped'
            error_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def save_message(task_id: str, agent_role: str, content: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO messages (task_id, agent_role, content)
        VALUES (?, ?, ?)
    ''', (task_id, agent_role, content))
    conn.commit()
    conn.close()

def get_history(task_id: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT agent_role, content, timestamp FROM messages
        WHERE task_id = ?
        ORDER BY timestamp ASC
    ''', (task_id,))
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        history.append({
            "role": "model" if row[0] != "user" else "user",
            "agent_name": row[0],
            "parts": [row[1]]
        })
    return history
