import streamlit as st
import sqlite3
import datetime
import pandas as pd
import time
import json
from contextlib import closing
from streamlit_js_eval import streamlit_js_eval

# --- Setup Datenbank ---
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

# --- Hilfsfunktionen ---
def get_setting(key, fallback=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else fallback

def generate_workdays(start, weeks):
    days = pd.date_range(start=start, periods=weeks * 7)
    return [d.date() for d in days if d.weekday() < 5]

# --- Login ---
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

# --- Haupt-App ---
def main_app(username):
    start_date = get_setting("start_date")
    weeks = get_setting("weeks")
    if not start_date or not weeks:
        st.warning("⚠️ Einstellungen unvollständig. Bitte Admin kontaktieren.")
        return

    start_date = datetime.datetime.strptime(start_date, "%Y-%m-%d").date()
    weeks = int(weeks)
    workdays = generate_workdays(start_date, weeks)

    # Prüfen, ob der Nutzer an der Reihe ist
    user_data = conn.execute("SELECT username, done FROM users ORDER BY ordering").fetchall()
    current_user = next((u[0] for u in user_data if u[1] == 0), None)
    if current_user != username:
        st.warning(f"⏳ Bitte warten Sie. Aktuell ist {current_user} an der Reihe.")
        return

    if 'selected_dates' not in st.session_state:
        existing = conn.execute("SELECT date FROM selections WHERE username = ?", (username,)).fetchall()
        st.session_state.selected_dates = [datetime.datetime.strptime(d[0], "%Y-%m-%d").date() for d in existing]

    st.subheader(f"👋 Willkommen {username}")
    st.write("Klicken Sie auf die gewünschten Arbeitstage:")

    for day in workdays:
        col = st.columns(7)[day.weekday()]
        label = day.strftime("%d.%m.%Y")
        clicked = col.button(
            label=label,
            key=f"day_{label}",
            help="Auswählen oder abwählen"
        )
        if clicked:
            if day in st.session_state.selected_dates:
                st.session_state.selected_dates.remove(day)
            else:
                st.session_state.selected_dates.append(day)
            st.experimental_rerun()

    parents = [u[0] for u in conn.execute("SELECT username FROM users ORDER BY ordering").fetchall()]
    n_days = len(workdays) // len(parents) + (1 if parents.index(username) < len(workdays) % len(parents) else 0)

    st.subheader("Ihre Auswahl")
    for d in sorted(st.session_state.selected_dates):
        st.write(f"- {d.strftime('%A, %d.%m.%Y')}")

    if len(st.session_state.selected_dates) == n_days:
        if st.button("✅ Auswahl abschließen"):
            conn.execute("DELETE FROM selections WHERE username = ?", (username,))
            for d in st.session_state.selected_dates:
                conn.execute("INSERT INTO selections (username, date) VALUES (?, ?)", (username, d.strftime("%Y-%m-%d")))
            conn.execute("UPDATE users SET done = 1 WHERE username = ?", (username,))
            conn.commit()
            st.success("Auswahl gespeichert! Der nächste Elternteil kann jetzt fortfahren.")
            streamlit_js_eval(js_expressions="parent.window.location.reload()")
    elif len(st.session_state.selected_dates) < n_days:
        st.info(f"Bitte wählen Sie noch {n_days - len(st.session_state.selected_dates)} weitere Tage.")
    else:
        st.error(f"Zu viele Tage ausgewählt. Maximal erlaubt: {n_days}.")

# --- Adminbereich ---
def admin_section():
    st.sidebar.subheader("🔐 Admin-Bereich")
    if st.sidebar.checkbox("Admin-Modus aktivieren"):
        pw = st.sidebar.text_input("Admin-Passwort", type="password")
        if pw == "admin":
            st.sidebar.success("Admin-Modus aktiviert")
            start = st.sidebar.date_input("Startdatum")
            weeks = st.sidebar.number_input("Anzahl Wochen", 1, 52, 4)
            if st.sidebar.button("Einstellungen speichern"):
                conn.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", ("start_date", start.strftime("%Y-%m-%d")))
                conn.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", ("weeks", str(weeks)))
                st.sidebar.success("Einstellungen gespeichert")
                time.sleep(1)
                st.rerun()

            st.sidebar.markdown("---")
            if st.sidebar.button("Demo-Nutzer importieren"):
                users = [f"eltern{i}" for i in range(1, 8)]
                conn.execute("DELETE FROM users")
                for i, user in enumerate(users):
                    conn.execute("INSERT INTO users (username, password, ordering) VALUES (?, ?, ?)", (user, user, i))
                st.sidebar.success("Demo-Nutzer wurden angelegt")
                time.sleep(1)
                st.rerun()

# --- App Start ---
st.title("📅 Kita-Dienstplan Tool")
admin_section()
user = login_section()
if user:
    main_app(user)
else:
    st.info("Bitte loggen Sie sich im Seitenmenü ein.")
