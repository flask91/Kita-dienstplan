import streamlit as st
import pandas as pd
import datetime
import sqlite3
from streamlit_calendar import calendar
import time

st.set_page_config(page_title="KITA Dienstplan Tool", layout="wide")
st.title("\U0001F4C5 KITA Dienstplan Generator")

# --- Datenbank Setup ---
conn = sqlite3.connect("kita_dienstplan.db")
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

# --- Adminbereich ---
st.sidebar.subheader("🛠️ Adminzugang")
if st.sidebar.checkbox("Admin-Modus anzeigen"):
    admin_pw = st.sidebar.text_input("Admin-Passwort", type="password")
    if admin_pw == "admin":
        st.sidebar.success("Admin eingeloggt")
        if st.sidebar.button("📥 Demo-Eltern importieren"):
            demo_parents = [f"eltern{i+1}" for i in range(7)]
            for i, name in enumerate(demo_parents):
                c.execute("INSERT OR IGNORE INTO users (username, password, ordering) VALUES (?, ?, ?)", (name, name, i))
            conn.commit()
            st.success("Demo-Eltern erfolgreich eingefügt!")

        st.sidebar.markdown("---")
        st.sidebar.markdown("### Benutzer verwalten")
        user_admin_data = pd.read_sql_query("SELECT * FROM users ORDER BY ordering", conn)
        for i, row in user_admin_data.iterrows():
            with st.sidebar.expander(f"👤 {row['username']}"):
                new_pw = st.text_input(f"Neues Passwort für {row['username']}", key=f"pw_{row['username']}")
                if st.button(f"Speichern für {row['username']}", key=f"btn_{row['username']}"):
                    c.execute("UPDATE users SET password = ? WHERE username = ?", (new_pw, row['username']))
                    conn.commit()
                    st.success(f"Passwort für {row['username']} geändert")

        if st.sidebar.button("🔄 Alle Eltern zurücksetzen"):
            c.execute("UPDATE users SET done = 0")
            c.execute("DELETE FROM selections")
            conn.commit()
            st.success("Alle Eltern zurückgesetzt")

        st.sidebar.markdown("---")
        st.sidebar.markdown("### Einstellungen speichern")
        start_date = st.sidebar.date_input("Startdatum", datetime.date.today())
        weeks = st.sidebar.number_input("Zeitraum in Wochen", min_value=1, max_value=52, value=7)
        parents_input = st.sidebar.text_area("Elternliste (ein Name pro Zeile)")

        if st.sidebar.button("📝 Einstellungen speichern"):
            c.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", ("start_date", start_date.strftime("%Y-%m-%d")))
            c.execute("REPLACE INTO settings (key, value) VALUES (?, ?)", ("weeks", str(weeks)))
            conn.commit()
            if parents_input:
                parents = [p.strip() for p in parents_input.strip().split("\n") if p.strip()]
                for i, name in enumerate(parents):
                    c.execute("INSERT OR IGNORE INTO users (username, password, ordering) VALUES (?, ?, ?)", (name, name, i))
                conn.commit()
            st.success("Einstellungen gespeichert")

# --- Benutzerlogin ---
st.sidebar.subheader("\U0001F511 Login")
username = st.sidebar.text_input("Benutzername")
password = st.sidebar.text_input("Passwort", type="password")

user_authenticated = False
if username and password:
    user = c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
    if user:
        user_authenticated = True
    else:
        st.sidebar.error("❌ Benutzername oder Passwort falsch")

if not user_authenticated:
    st.stop()

# --- Einstellungen laden ---
def get_setting(key, fallback=None):
    row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row[0] if row else fallback

start_date_str = get_setting("start_date")
weeks_str = get_setting("weeks")
if not start_date_str or not weeks_str:
    st.warning("⚠️ Einstellungen unvollständig. Bitte Admin kontaktieren.")
    st.stop()

start_date = datetime.datetime.strptime(start_date_str, "%Y-%m-%d").date()
weeks = int(weeks_str)

# Eltern laden
parents = [row[0] for row in c.execute("SELECT username FROM users ORDER BY ordering").fetchall()]
if len(parents) == 0:
    st.warning("⚠️ Keine Eltern vorhanden. Bitte Admin kontaktieren.")
    st.stop()

user_data = c.execute("SELECT username, ordering, done FROM users ORDER BY ordering ASC").fetchall()
current_index = next((i for i, u in enumerate(user_data) if u[2] == 0), None)

if current_index is None:
    st.success("✅ Alle Eltern haben ihre Auswahl abgeschlossen!")
    st.stop()
elif user_data[current_index][0] != username:
    st.warning(f"⏳ Bitte warte, bis du an der Reihe bist. Aktuell ist **{user_data[current_index][0]}** dran.")
    st.stop()

# --- Kalenderlogik ---
def generate_workdays(start, weeks):
    days = pd.date_range(start=start, periods=weeks * 7)
    weekdays = days[days.weekday < 5]  # Nur Mo–Fr
    return [d.date() for d in list(weekdays)]

def get_calendar_view(start_date, weeks):
    end_date = start_date + datetime.timedelta(weeks=weeks)
    month_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
    return {
        "initialView": "dayGridMonth",
        "selectable": True,
        "selectMirror": True,
        "editable": True,
        "dayMaxEvents": True,
        "locale": "de",
        "height": 600,
        "headerToolbar": {
            "left": "prev,next today",
            "center": "title",
            "right": "dayGridMonth,timeGridWeek,timeGridDay"
        },
        "visibleRange": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d")
        }
    }

# Arbeitstage generieren
workdays = generate_workdays(start_date, weeks)
total_days = len(workdays)
days_per_parent = total_days // len(parents)
rest_days = total_days % len(parents)
n_days = days_per_parent + (1 if current_index < rest_days else 0)

# Session State für Auswahl initialisieren
if 'selected_dates' not in st.session_state:
    st.session_state.selected_dates = []

# Bereits getätigte Auswahl laden
existing_selections = c.execute("SELECT date FROM selections WHERE username = ?", (username,)).fetchall()
existing_dates = [datetime.datetime.strptime(d[0], "%Y-%m-%d").date() for d in existing_selections]

# Kalender-Events erstellen
events = []
for date in existing_dates:
    events.append({
        "title": "Ausgewählt",
        "start": date.strftime("%Y-%m-%d"),
        "end": date.strftime("%Y-%m-%d"),
        "color": "#FFA500",
        "allDay": True
    })

# Kalender anzeigen
calendar_options = get_calendar_view(start_date, weeks)

st.markdown(f"""
    <div style='background-color:#fffae6;padding:1rem;border-radius:0.5rem;border:1px solid #f0c36d;'>
        <h2 style='text-align:center;'>\u2728 Jetzt ist <span style='color:#d47b00;'>{username}</span> an der Reihe!</h2>
        <p style='text-align:center;font-size:1.2rem;'>Du musst <strong>{n_days} Tage</strong> auswählen</p>
    </div>
""", unsafe_allow_html=True)

# Kalender rendern
calendar_container = st.empty()
with calendar_container.container():
    cal = calendar(events=events, options=calendar_options, key=f"calendar_{username}")

# Auswahl verarbeiten
if cal.get("select"):
    selected_date = datetime.datetime.strptime(cal["select"]["start"], "%Y-%m-%d").date()
    
    if selected_date in workdays:
        if selected_date in st.session_state.selected_dates:
            st.session_state.selected_dates.remove(selected_date)
        else:
            if len(st.session_state.selected_dates) < n_days:
                st.session_state.selected_dates.append(selected_date)
            else:
                st.warning(f"Du kannst maximal {n_days} Tage auswählen")
        
        # Kurze Verzögerung um UI-Update zu ermöglichen
        time.sleep(0.3)
        st.experimental_rerun()

# Auswahl-Status anzeigen
col1, col2 = st.columns(2)
with col1:
    st.subheader("Deine Auswahl")
    if st.session_state.selected_dates:
        sorted_dates = sorted(st.session_state.selected_dates)
        for d in sorted_dates:
            st.markdown(f"- {d.strftime('%d.%m.%Y')} ({d.strftime('%A')})")
    else:
        st.info("Noch keine Tage ausgewählt")

with col2:
    st.subheader("Auswahl-Status")
    if len(st.session_state.selected_dates) > n_days:
        st.error(f"❌ Zu viele Tage ausgewählt! Max: {n_days}")
    elif len(st.session_state.selected_dates) < n_days:
        st.info(f"ℹ️ Noch nicht alle Tage ausgewählt ({len(st.session_state.selected_dates)}/{n_days})")
    else:
        st.success(f"✅ Perfekt! Du hast genau {n_days} Tage ausgewählt.")

# Auswahl absenden
if st.button("✅ Auswahl absenden und freigeben", key="submit_btn"):
    if len(st.session_state.selected_dates) != n_days:
        st.warning(f"Bitte genau {n_days} Tage auswählen.")
    else:
        c.execute("DELETE FROM selections WHERE username = ?", (username,))
        for d in st.session_state.selected_dates:
            c.execute("INSERT INTO selections (username, date) VALUES (?, ?)", (username, d.strftime("%Y-%m-%d")))
        c.execute("UPDATE users SET done = 1 WHERE username = ?", (username,))
        conn.commit()
        st.success("Gespeichert! Jetzt darf der nächste Elternteil sich einloggen.")
        st.session_state.selected_dates = []
        time.sleep(2)
        st.experimental_rerun()

# Übersicht
st.subheader("\U0001F4CA Bisherige Auswahl")
df = pd.read_sql_query("SELECT * FROM selections", conn)
if not df.empty:
    df['Datum'] = pd.to_datetime(df['date'])
    df['Wochentag'] = df['Datum'].dt.strftime('%A')
    df = df.drop(columns=['date'])
    df = df.rename(columns={'username': 'Eltern'})
    df = df.sort_values("Datum")
    st.dataframe(df)
    csv = df.to_csv(index=False).encode('utf-8')
    st.download_button("\U0001F4E5 Plan als CSV herunterladen", csv, "dienstplan.csv", "text/csv")
