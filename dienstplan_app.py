import streamlit as st
import sqlite3
import datetime
import pandas as pd
from streamlit_calendar import calendar
import time
import json
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

# --- Einstellungen & Hilfsfunktionen ---
def get_setting(key, fallback=None):
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else fallback

def generate_workdays(start, weeks):
    days = pd.date_range(start=start, periods=weeks * 7)
    return [d.date() for d in days if d.weekday() < 5]

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

# --- Hauptbereich ---
def main_app(username):
    # Einstellungen laden
    start_date_str = get_setting("start_date")
    weeks_str = get_setting("weeks")

    if not start_date_str or not weeks_str:
        st.warning("⚠️ Einstellungen unvollständig. Bitte Admin kontaktieren.")
        return

    start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
    weeks = int(weeks_str)
    workdays = generate_workdays(start_date, weeks)

    # Wer ist an der Reihe?
    user_data = conn.execute("SELECT username, done FROM users ORDER BY ordering").fetchall()
    current_user = next((u[0] for u in user_data if u[1] == 0), None)

    if current_user is None:
        st.success("✅ Alle Eltern haben abgeschlossen!")
        return

    if current_user != username:
        st.warning(f"⏳ Bitte warten Sie. Aktuell ist {current_user} an der Reihe.")
        return

    # Auswahl laden
    if 'selected_dates' not in st.session_state:
        existing = conn.execute("SELECT date FROM selections WHERE username = ?", (username,)).fetchall()
        st.session_state.selected_dates = [datetime.datetime.strptime(d[0], "%Y-%m-%d").date() for d in existing]

    # Kalenderoptionen
    calendar_options = {
        "initialView": "dayGridMonth",
        "selectable": True,
        "editable": True,
        "locale": "de",
        "height": 600,
        "validRange": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": (start_date + datetime.timedelta(weeks=weeks)).strftime("%Y-%m-%d")
        }
    }

    events = [{
        "title": "Ausgewählt",
        "start": d.strftime("%Y-%m-%d"),
        "end": d.strftime("%Y-%m-%d"),
        "color": "#FFA500",
        "allDay": True
    } for d in st.session_state.selected_dates]

    st.markdown(f"""
        <div style='background:#f0f2f6;padding:1rem;border-radius:0.5rem;margin-bottom:1rem;'>
            <h2 style='text-align:center;'>👋 Hallo {username}</h2>
            <p style='text-align:center;'>Bitte wählen Sie Ihre Tage im Kalender</p>
        </div>
    """, unsafe_allow_html=True)

    cal = calendar(events=events, options=calendar_options, key="main_calendar")

    # ✅ Auswahlverarbeitung (Fix)
    if cal and cal.get("start"):
        selected_date = datetime.datetime.strptime(cal["start"][:10], "%Y-%m-%d").date()

        if selected_date in workdays:
            if selected_date in st.session_state.selected_dates:
                st.session_state.selected_dates.remove(selected_date)
            else:
                st.session_state.selected_dates.append(selected_date)

            time.sleep(0.2)
            st.experimental_rerun()

    # Fortschritt anzeigen
    parents = [u[0] for u in user_data]
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
        selected_count = len(st.session_state.selected_dates)
        if selected_count == n_days:
            st.success(f"✅ {n_days} Tage ausgewählt")
        elif selected_count < n_days:
            st.warning(f"⚠️ Noch {n_days - selected_count} Tage nötig")
        else:
            st.error(f"❌ Zu viele Tage ausgewählt (max. {n_days})")

    if st.button("📤 Auswahl bestätigen", type="primary"):
        if len(st.session_state.selected_dates) == n_days:
            conn.execute("DELETE FROM selections WHERE username = ?", (username,))
            for d in st.session_state.selected_dates:
                conn.execute("INSERT INTO selections (username, date) VALUES (?, ?)", (username, d.strftime("%Y-%m-%d")))
            conn.execute("UPDATE users SET done = 1 WHERE username = ?", (username,))
            conn.commit()
            st.success("Erfolgreich gespeichert!")
            st.session_state.selected_dates = []
            time.sleep(1.5)
            st.experimental_rerun()
        else:
            st.error(f"Bitte genau {n_days} Tage auswählen")

# --- Start ---
st.title("📅 KITA Dienstplan")
username = login_section()
if username:
    main_app(username)
else:
    st.info("Bitte im Seitenmenü einloggen.")
