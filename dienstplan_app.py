import streamlit as st
import sqlite3
import datetime
import pandas as pd
from streamlit_calendar import calendar
import time
import json
import io
from contextlib import closing

# --- Datenbank Setup ---
@st.cache_resource
def init_db():
    conn = sqlite3.connect("kita_dienstplan.db", isolation_level=None)
    conn.row_factory = sqlite3.Row  # Für bessere Dict-Konvertierung
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            password TEXT,
            ordering INTEGER,
            done INTEGER DEFAULT 0
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS selections (
            username TEXT,
            date TEXT,
            PRIMARY KEY(username, date)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    return conn

conn = init_db()

# --- Backup & Restore Funktionen ---
def create_backup():
    """Erstellt ein vollständiges Backup aller Tabellen"""
    backup = {}
    tables = ["users", "selections", "settings"]
    
    with closing(conn.cursor()) as cursor:
        for table in tables:
            cursor.execute(f"SELECT * FROM {table}")
            backup[table] = [dict(row) for row in cursor.fetchall()]
    
    backup["metadata"] = {
        "timestamp": datetime.datetime.now().isoformat(),
        "version": "1.0",
        "tables": tables
    }
    
    return json.dumps(backup, indent=2)

def restore_backup(backup_file):
    """Stellt ein Backup aus einer JSON-Datei wieder her"""
    try:
        backup = json.load(backup_file)
        
        with conn:  # Transaction
            # Temporäre Tabellen für sicheren Restore
            conn.execute("DROP TABLE IF EXISTS temp_users")
            conn.execute("DROP TABLE IF EXISTS temp_selections")
            conn.execute("DROP TABLE IF EXISTS temp_settings")
            
            # Originaltabellenstruktur kopieren
            conn.execute("CREATE TABLE temp_users AS SELECT * FROM users WHERE 1=0")
            conn.execute("CREATE TABLE temp_selections AS SELECT * FROM selections WHERE 1=0")
            conn.execute("CREATE TABLE temp_settings AS SELECT * FROM settings WHERE 1=0")
            
            # Daten einfügen
            for table in backup:
                if table.startswith("temp_"):
                    continue
                
                if table in ["users", "selections", "settings"]:
                    temp_table = f"temp_{table}"
                    for row in backup[table]:
                        columns = ", ".join(row.keys())
                        placeholders = ", ".join("?" * len(row))
                        conn.execute(
                            f"INSERT INTO {temp_table} ({columns}) VALUES ({placeholders})",
                            list(row.values())
                        )
            
            # Validierung
            user_count = conn.execute("SELECT COUNT(*) FROM temp_users").fetchone()[0]
            if user_count == 0:
                raise ValueError("Backup enthält keine Benutzerdaten")
            
            # Originaltabellen ersetzen
            conn.execute("DROP TABLE users")
            conn.execute("DROP TABLE selections")
            conn.execute("DROP TABLE settings")
            
            conn.execute("ALTER TABLE temp_users RENAME TO users")
            conn.execute("ALTER TABLE temp_selections RENAME TO selections")
            conn.execute("ALTER TABLE temp_settings RENAME TO settings")
            
        return True, f"Erfolgreich wiederhergestellt! {user_count} Benutzer importiert."
    except Exception as e:
        conn.rollback()
        return False, f"Fehler beim Restore: {str(e)}"

# --- Erweiterte Admin-Funktionen ---
def backup_restore_section():
    st.sidebar.subheader("💾 Backup & Restore")
    
    col1, col2 = st.sidebar.columns(2)
    
    with col1:
        if st.button("Backup erstellen"):
            backup_data = create_backup()
            st.download_button(
                label="Backup herunterladen",
                data=backup_data,
                file_name=f"kita_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M')}.json",
                mime="application/json"
            )
    
    with col2:
        backup_file = st.file_uploader("Backup hochladen", type=["json"])
        if backup_file and st.button("Backup wiederherstellen"):
            with st.spinner("Backup wird eingespielt..."):
                success, message = restore_backup(backup_file)
                if success:
                    st.success(message)
                    time.sleep(3)
                    st.rerun()
                else:
                    st.error(message)

def admin_functions():
    st.sidebar.subheader("🛠️ Erweiterte Admin-Tools")
    
    # Backup & Restore
    if st.sidebar.checkbox("💾 Backup-Verwaltung anzeigen"):
        backup_restore_section()
    
    # Session Reset
    if st.sidebar.checkbox("🔄 Session zurücksetzen"):
        if st.sidebar.button("Bestätigen: Session zurücksetzen"):
            keys = list(st.session_state.keys())
            for key in keys:
                if not key.startswith('_'):  # Behalte interne Streamlit-Keys
                    del st.session_state[key]
            st.success("Session-States zurückgesetzt!")
            time.sleep(2)
            st.rerun()
    
    # Benutzerverwaltung
    if st.sidebar.checkbox("👥 Benutzerverwaltung"):
        users = pd.read_sql("SELECT username FROM users ORDER BY ordering", conn)
        
        col1, col2 = st.sidebar.columns(2)
        
        with col1:
            user_to_delete = st.selectbox("Benutzer löschen", users['username'])
            if st.button("Benutzer entfernen"):
                with conn:
                    conn.execute("DELETE FROM users WHERE username = ?", (user_to_delete,))
                    conn.execute("DELETE FROM selections WHERE username = ?", (user_to_delete,))
                st.success(f"Benutzer {user_to_delete} gelöscht!")
                time.sleep(2)
                st.rerun()
        
        with col2:
            new_user = st.text_input("Neuer Benutzername")
            new_pw = st.text_input("Passwort", type="password")
            if st.button("Benutzer hinzufügen"):
                if new_user and new_pw:
                    max_order = conn.execute("SELECT MAX(ordering) FROM users").fetchone()[0] or 0
                    with conn:
                        conn.execute(
                            "INSERT INTO users (username, password, ordering) VALUES (?, ?, ?)",
                            (new_user, new_pw, max_order + 1)
                    st.success(f"Benutzer {new_user} angelegt!")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Benutzername und Passwort benötigt")

# --- Integration in bestehenden Code ---
def admin_section():
    st.sidebar.subheader("🔐 Admin-Bereich")
    if st.sidebar.checkbox("Admin-Modus aktivieren"):
        admin_pw = st.sidebar.text_input("Admin-Passwort", type="password", key="admin_pw")
        
        if admin_pw == "admin":  # In Produktion durch sichere Methode ersetzen!
            st.sidebar.success("Admin-Zugang aktiviert")
            admin_functions()
        elif admin_pw:
            st.sidebar.error("Falsches Admin-Passwort")

# --- Hauptanwendung ---
def main_app(username):
    # ... (vorheriger Code bleibt unverändert)
    pass

# --- App-Logik ---
admin_section()
username = login_section()  # Ihre existierende Login-Funktion

if username:
    main_app(username)
else:
    st.info("Bitte melden Sie sich im Seitenmenü an")
