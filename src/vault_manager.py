import os
import re
import sqlite3
from datetime import datetime
from .db import DB_PATH

def sync_vault(vault_path: str):
    """Escanea el vault completo y sincroniza la DB."""
    if not vault_path:
        return
    
    vault_path = vault_path.strip('"').strip("'").strip()
    if not os.path.exists(vault_path):
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        for d in dirs:
            full_path = os.path.join(root, d)
            rel_path = os.path.relpath(full_path, vault_path).replace('\\', '/')
            cursor.execute('''
                INSERT INTO vault_nodes (path, name, type)
                VALUES (?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET last_seen=CURRENT_TIMESTAMP
            ''', (rel_path, d, 'folder'))

        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, vault_path).replace('\\', '/')
            sync_node(vault_path, rel_path, cursor)

    conn.commit()
    conn.close()

def sync_node(vault_base: str, rel_path: str, cursor):
    """Sincroniza un solo archivo o carpeta con la DB."""
    full_path = os.path.join(vault_base, rel_path)
    if not os.path.exists(full_path):
        return

    name = os.path.basename(rel_path)
    ntype = 'folder' if os.path.isdir(full_path) else 'file'
    content = ""
    
    if ntype == 'file':
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except:
            pass

    cursor.execute('''
        INSERT INTO vault_nodes (path, name, type, content)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(path) DO UPDATE SET content=excluded.content, last_seen=CURRENT_TIMESTAMP
    ''', (rel_path, name, ntype, content))

    if ntype == 'file' and rel_path.lower().endswith('.md'):
        extract_links(rel_path, content, cursor)
        extract_tags(rel_path, content, cursor)

def extract_links(source_path: str, content: str, cursor):
    """Extrae [[wikilinks]] mejorados."""
    cursor.execute('DELETE FROM vault_links WHERE source_path = ?', (source_path,))
    
    # Regex mejorado para manejar wikilinks con alias y bloques
    pattern = r"\[\[([^\]|#]+)(?:[|#][^\]]+)?\]\]"
    matches = re.finditer(pattern, content)
    
    seen = set()
    for match in matches:
        target_name = match.group(1).strip()
        if target_name not in seen:
            start = max(0, match.start() - 40)
            end = min(len(content), match.end() + 40)
            context = content[start:end].replace('\n', ' ').strip()
            
            cursor.execute('''
                INSERT INTO vault_links (source_path, target_name, context)
                VALUES (?, ?, ?)
            ''', (source_path, target_name, context))
            seen.add(target_name)

def extract_tags(source_path: str, content: str, cursor):
    """Extrae #tags del contenido y frontmatter."""
    cursor.execute('DELETE FROM vault_tags WHERE node_path = ?', (source_path,))
    
    # Busca tags tipo #tag o en frontmatter tags: [tag]
    # Regex simple para #tag (letras, números, _, -, /)
    tag_pattern = r"(?<!\w)#([a-zA-Z0-9_\-/]+)"
    matches = re.finditer(tag_pattern, content)
    
    seen = set()
    for match in matches:
        tag = match.group(1).lower()
        if tag not in seen:
            cursor.execute('''
                INSERT INTO vault_tags (node_path, tag)
                VALUES (?, ?)
            ''', (source_path, tag))
            seen.add(tag)

def get_vault_tree() -> str:
    """Devuelve el árbol jerárquico."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT path, type FROM vault_nodes ORDER BY path ASC')
    rows = cursor.fetchall()
    conn.close()
    
    tree = []
    for path, ntype in rows:
        depth = path.count('/')
        indent = "  " * depth
        prefix = "📁 " if ntype == 'folder' else "📄 "
        tree.append(f"{indent}{prefix}{os.path.basename(path)}")
    
    return "\n".join(tree) if tree else "Vault empty."

def get_note_relationships(rel_path: str) -> str:
    """Obtiene links salientes y entrantes (backlinks) de una nota."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Salientes
    cursor.execute('SELECT target_name FROM vault_links WHERE source_path = ?', (rel_path,))
    outgoing = [r[0] for r in cursor.fetchall()]
    
    # Entrantes (Basado en el nombre de la nota)
    note_name = os.path.splitext(os.path.basename(rel_path))[0]
    cursor.execute('SELECT source_path FROM vault_links WHERE target_name = ?', (note_name,))
    incoming = [r[0] for r in cursor.fetchall()]
    
    # Tags
    cursor.execute('SELECT tag FROM vault_tags WHERE node_path = ?', (rel_path,))
    tags = [r[0] for r in cursor.fetchall()]
    
    conn.close()
    
    res = f"Relaciones para: {rel_path}\n"
    res += f"Tags: {', '.join(tags) if tags else 'Ninguno'}\n"
    res += f"Links salientes: {', '.join(outgoing) if outgoing else 'Ninguno'}\n"
    res += f"Backlinks (quién la cita): {', '.join(incoming) if incoming else 'Ninguno'}"
    return res
