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
    conn.row_factory = sqlite3.Row
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
        
        with conn:
            conn.execute("DROP TABLE IF EXISTS temp_users")
            conn.execute("DROP TABLE IF EXISTS temp_selections")
            conn.execute("DROP TABLE IF EXISTS temp_settings")
            
            conn.execute("CREATE TABLE temp_users AS SELECT * FROM users WHERE 1=0")
            conn.execute("CREATE TABLE temp_selections AS SELECT * FROM selections WHERE 1=0")
            conn.execute("CREATE TABLE temp_settings AS SELECT * FROM settings WHERE 1=0")
            
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
            
            user_count = conn.execute("SELECT COUNT(*) FROM temp_users").fetchone()[0]
            if user_count == 0:
                raise ValueError("Backup enthält keine Benutzerdaten")
            
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

# --- Backup & Restore UI ---
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

# --- Erweiterte Admin-Funktionen ---
def admin_functions():
    st.sidebar.subheader("🛠️ Erweiterte Admin-Tools")
    
    if st.sidebar.checkbox("💾 Backup-Verwaltung anzeigen"):
        backup_restore_section()
    
    if st.sidebar.checkbox("🔄 Session zurücksetzen"):
        if st.sidebar.button("Bestätigen: Session zurücksetzen"):
            keys = list(st.session_state.keys())
            for key in keys:
                if not key.startswith('_'):
                    del st.session_state[key]
            st.success("Session-States zurückgesetzt!")
            time.sleep(2)
            st.rerun()
    
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
                        )
                    st.success(f"Benutzer {new_user} angelegt!")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("Benutzername und Passwort benötigt")

# --- Login-Section ---
def login_section():
    st.sidebar.subheader("🔑 Login")
    username = st.sidebar.text_input("Benutzername")
    password = st.sidebar.text_input("Passwort", type="password")
    
    if username and password:
        user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", 
                          (username, password)).fetchone()
        if user:
            return username
        else:
            st.sidebar.error("Falsche Anmeldedaten")
    return None

# --- Admin-Section ---
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
    # Einstellungen laden
    start_date = datetime.datetime.strptime(get_setting("start_date"), "%Y-%m-%d").date()
    weeks = int(get_setting("weeks"))
    workdays = generate_workdays(start_date, weeks)
    
    # Benutzerstatus prüfen
    user_data = conn.execute("SELECT username, done FROM users ORDER BY ordering").fetchall()
    current_user = next((u[0] for u in user_data if u[1] == 0), None)
    
    if current_user is None:
        st.success("✅ Alle Eltern haben abgeschlossen!")
        return
    
    if current_user != username:
        st.warning(f"⏳ Bitte warten Sie. Aktuell ist {current_user} an der Reihe.")
        return
    
    # Session State für Auswahl
    if 'selected_dates' not in st.session_state:
        existing = conn.execute("SELECT date FROM selections WHERE username = ?", (username,)).fetchall()
        st.session_state.selected_dates = [datetime.datetime.strptime(d[0], "%Y-%m-%d").date() for d in existing]
    
    # Kalender konfigurieren
    calendar_options = {
        "initialView": "dayGridMonth",
        "selectable": True,
        "selectMirror": True,
        "editable": True,
        "locale": "de",
        "height": 600,
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,timeGridDay"
        },
        "validRange": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": (start_date + datetime.timedelta(weeks=weeks)).strftime("%Y-%m-%d")
        }
    }
    
    # Events für Kalender
    events = [{
        "title": "Ausgewählt",
        "start": d.strftime("%Y-%m-%d"),
        "end": d.strftime("%Y-%m-%d"),
        "color": "#FFA500",
        "allDay": True
    } for d in st.session_state.selected_dates]
    
    # UI Darstellung
    st.markdown(f"""
        <div style='background:#f8f9fa;padding:1rem;border-radius:0.5rem;margin-bottom:1rem;'>
            <h2 style='text-align:center;color:#2c3e50;'>👋 Hallo {username}!</h2>
            <p style='text-align:center;'>Bitte wählen Sie Ihre Tage aus</p>
        </div>
    """, unsafe_allow_html=True)
    
    # Kalender rendern
    cal = calendar(events=events, options=calendar_options, key="main_calendar")
    
    # Auswahl verarbeiten
    if "select" in cal:
        selected_date = datetime.datetime.strptime(cal["select"]["start"], "%Y-%m-%d").date()
        
        if selected_date in workdays:
            if selected_date in st.session_state.selected_dates:
                st.session_state.selected_dates.remove(selected_date)
            else:
                st.session_state.selected_dates.append(selected_date)
            
            time.sleep(0.3)
            st.experimental_rerun()
    
    # Auswahl-Status
    parents = [u[0] for u in conn.execute("SELECT username FROM users ORDER BY ordering").fetchall()]
    n_days = len(workdays) // len(parents) + (1 if parents.index(username) < len(workdays) % len(parents) else 0)
    
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Ihre Auswahl")
        if st.session_state.selected_dates:
            for d in sorted(st.session_state.selected_dates):
                st.write(f"- {d.strftime('%d.%m.%Y')} ({d.strftime('%A')})")
        else:
            st.info("Noch keine Tage ausgewählt")
    
    with col2:
        st.subheader("Status")
        if len(st.session_state.selected_dates) == n_days:
            st.success(f"✅ Perfekt! {n_days} Tage ausgewählt")
        elif len(st.session_state.selected_dates) < n_days:
            st.warning(f"⚠️ Noch {n_days - len(st.session_state.selected_dates)} Tage benötigt")
        else:
            st.error(f"❌ Zu viele Tage ausgewählt (max {n_days})")
    
    # Absenden-Button
    if st.button("📤 Auswahl bestätigen", type="primary"):
        if len(st.session_state.selected_dates) == n_days:
            conn.execute("DELETE FROM selections WHERE username = ?", (username,))
            for d in st.session_state.selected_dates:
                conn.execute("INSERT INTO selections (username, date) VALUES (?, ?)", 
                           (username, d.strftime("%Y-%m-%d")))
            conn.execute("UPDATE users SET done = 1 WHERE username = ?", (username,))
            conn.commit()
            st.success("Erfolgreich gespeichert! Der nächste Elternteil kann sich jetzt anmelden.")
            st.session_state.selected_dates = []
            time.sleep(2)
            st.experimental_rerun()
        else:
            st.error(f"Bitte genau {n_days} Tage ausgewählt")

# --- Hilfsfunktionen ---
def get_setting(key, fallback=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else fallback

def generate_workdays(start, weeks):
    days = pd.date_range(start=start, periods=weeks * 7)
    return [d.date() for d in days if d.weekday() < 5]

# --- App-Logik ---
st.title("📅 KITA Dienstplan Generator")
admin_section()
username = login_section()

if username:
    main_app(username)
else:
    st.info("Bitte melden Sie sich im Seitenmenü an")

# Übersicht aller Auswahlen
st.markdown("---")
st.subheader("📊 Gesamtübersicht")
df = pd.read_sql("SELECT username, date FROM selections ORDER BY date", conn)
if not df.empty:
    df["Datum"] = pd.to_datetime(df["date"])
    df["Wochentag"] = df["Datum"].dt.strftime("%A")
    st.dataframe(df.drop(columns=["date"]).rename(columns={"username": "Eltern"}))
    
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("📥 Als CSV exportieren", csv, "kita_dienstplan.csv", "text/csv")
else:
    st.info("Noch keine Auswahlen vorhanden")
