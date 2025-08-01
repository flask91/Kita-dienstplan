import streamlit as st
import pandas as pd
import datetime
import random
import sqlite3
from streamlit_calendar import calendar

st.set_page_config(page_title="KITA Dienstplan Tool")
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

if user_authenticated:
    st.sidebar.success(f"✅ Eingeloggt als {username}")
else:
    st.stop()

# Einstellungen
st.sidebar.header("\U0001F527 Einstellungen")
start_date = st.sidebar.date_input("Startdatum", datetime.date.today())
weeks = st.sidebar.number_input("Zeitraum in Wochen", min_value=1, max_value=52, value=7)
parents_input = st.sidebar.text_area("Elternliste (ein Name pro Zeile)")
mode = st.sidebar.radio("Kalenderauswahlmodus", ["Ein Kalender für alle", "Ein Kalender pro Person"])

# Eltern speichern, falls noch nicht in DB
def sync_parents(parents):
    for i, name in enumerate(parents):
        c.execute("INSERT OR IGNORE INTO users (username, password, ordering) VALUES (?, ?, ?)", (name, name, i))
    conn.commit()

# --- Kalenderhilfe ---
def generate_workdays(start, weeks):
    days = pd.date_range(start=start, periods=weeks * 7)
    weekdays = days[days.weekday < 5]  # Nur Mo–Fr
    return list(weekdays)

def get_calendar_view(start_date, weeks):
    end_date = start_date + datetime.timedelta(weeks=weeks)
    month_diff = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month) + 1
    return {
        "initialView": "dayGridMonth",
        "selectable": True,
        "locale": "de",
        "editable": False,
        "height": 500 + month_diff * 100,
        "visibleRange": {
            "start": start_date.strftime("%Y-%m-%d"),
            "end": end_date.strftime("%Y-%m-%d")
        }
    }

if parents_input:
    parents = [p.strip() for p in parents_input.strip().split("\n") if p.strip()]
    if len(parents) == 0:
        st.warning("Bitte mindestens eine Person angeben.")
    else:
        sync_parents(parents)
        user_data = c.execute("SELECT username, ordering, done FROM users ORDER BY ordering ASC").fetchall()
        current_index = next((i for i, u in enumerate(user_data) if u[2] == 0), None)

        if current_index is None:
            st.success("✅ Alle Eltern haben ihre Auswahl abgeschlossen!")
        elif user_data[current_index][0] != username:
            st.warning(f"⏳ Bitte warte, bis du an der Reihe bist. Aktuell ist **{user_data[current_index][0]}** dran.")
            st.stop()

        workdays = generate_workdays(start_date, weeks)
        total_days = len(workdays)
        days_per_parent = total_days // len(parents)
        rest_days = total_days % len(parents)

        st.markdown(f"**Verfügbare Werktage:** {total_days} ({start_date} bis {start_date + datetime.timedelta(weeks=weeks)})")
        st.markdown(f"**Tage pro Elternteil:** {days_per_parent} (+1 für {rest_days} Personen)")

        n_days = days_per_parent + (1 if current_index < rest_days else 0)
        calendar_options = get_calendar_view(start_date, weeks)

        st.markdown(f"""
            <div style='background-color:#fffae6;padding:1rem;border-radius:0.5rem;border:1px solid #f0c36d;'>
                <h2 style='text-align:center;'>\u2728 Jetzt ist <span style='color:#d47b00;'>{username}</span> an der Reihe!</h2>
            </div>
        """, unsafe_allow_html=True)

        events = calendar(
            options=calendar_options,
            key=f"calendar_{username}"
        )

        selected = [pd.to_datetime(e['start'][:10]) for e in events.get("selected", []) if pd.to_datetime(e['start'][:10]) in workdays]

        if len(selected) > n_days:
            st.error(f"❌ Du hast zu viele Tage ausgewählt! Max: {n_days}")
        elif len(selected) < n_days:
            st.info(f"ℹ️ Du hast noch nicht alle Tage ausgewählt ({len(selected)}/{n_days})")

        if len(selected) == n_days:
            if st.button("✅ Auswahl speichern & weiter"):
                # Auswahl speichern
                c.execute("DELETE FROM selections WHERE username = ?", (username,))
                for d in selected:
                    c.execute("INSERT INTO selections (username, date) VALUES (?, ?)", (username, d.strftime("%Y-%m-%d")))
                c.execute("UPDATE users SET done = 1 WHERE username = ?", (username,))
                conn.commit()
                st.success("Gespeichert! Bitte nächste Person einloggen.")
                st.stop()

        # Übersicht
        st.subheader("\U0001F4CA Übersicht")
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
else:
    st.info("Bitte gib die Elternliste ein, um zu starten.")
