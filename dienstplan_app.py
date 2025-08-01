import streamlit as st
import pandas as pd
import datetime
import random

from streamlit_calendar import calendar

st.set_page_config(page_title="KITA Dienstplan Tool")
st.title("📅 KITA Dienstplan Generator")

# Eingaben
st.sidebar.header("🔧 Einstellungen")
start_date = st.sidebar.date_input("Startdatum", datetime.date.today())
weeks = st.sidebar.number_input("Zeitraum in Wochen", min_value=1, max_value=52, value=7)
parents_input = st.sidebar.text_area("Elternliste (ein Name pro Zeile)")
mode = st.sidebar.radio("Kalenderauswahlmodus", ["Ein Kalender für alle", "Ein Kalender pro Person"])


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
        if st.sidebar.button("Zufällige Reihenfolge erstellen"):
            random.shuffle(parents)

        st.subheader("👪 Eltern in Reihenfolge")
        st.write("Falls nötig, kannst du die Reihenfolge der Eltern hier manuell anpassen:")
        new_order_input = st.text_area("Reihenfolge manuell ändern (ein Name pro Zeile):", "\n".join(parents))

        new_order = [name.strip() for name in new_order_input.strip().split("\n") if name.strip()]
        if set(new_order) == set(parents) and len(new_order) == len(parents):
            parents = new_order
        else:
            st.warning("Die manuelle Reihenfolge ist ungültig oder unvollständig. Ursprüngliche Reihenfolge wird beibehalten.")

        workdays = generate_workdays(start_date, weeks)
        total_days = len(workdays)
        days_per_parent = total_days // len(parents)
        rest_days = total_days % len(parents)

        st.markdown(f"**Verfügbare Werktage:** {total_days} ({start_date} bis {start_date + datetime.timedelta(weeks=weeks)})")
        st.markdown(f"**Tage pro Elternteil:** {days_per_parent} (+1 für {rest_days} Personen)")

        selections = {}
        remaining_days = set(workdays)
        calendar_options = get_calendar_view(start_date, weeks)

        if mode == "Ein Kalender für alle":
            st.markdown("### 🗓️ Gemeinsamer Kalender")
            all_events = calendar(
                options=calendar_options,
                key="shared_calendar"
            )

            selected_dates = [pd.to_datetime(e['start'][:10]) for e in all_events.get("selected", []) if pd.to_datetime(e['start'][:10]) in workdays]

            per_parent_count = {p: 0 for p in parents}
            for i, date in enumerate(selected_dates):
                p = parents[i % len(parents)]
                selections.setdefault(p, []).append(date)
                remaining_days.discard(date)

        else:
            for idx, parent in enumerate(parents):
                st.markdown(f"### 🧑‍🍼 {parent}")
                n_days = days_per_parent + (1 if idx < rest_days else 0)
                events = calendar(
                    options=calendar_options,
                    key=f"calendar_{parent}"
                )

                selected = [pd.to_datetime(e['start'][:10]) for e in events.get("selected", []) if pd.to_datetime(e['start'][:10]) in workdays]

                if len(selected) > n_days:
                    st.error(f"❌ Du hast zu viele Tage ausgewählt! Max: {n_days}")
                else:
                    selections[parent] = selected
                    remaining_days -= set(selected)

        st.subheader("📊 Übersicht")
        table = []
        for p in parents:
            for d in selections.get(p, []):
                table.append({"Eltern": p, "Datum": d.strftime('%Y-%m-%d'), "Wochentag": d.strftime('%A')})

        df_plan = pd.DataFrame(table)
        if not df_plan.empty and "Datum" in df_plan.columns:
            df_plan = df_plan.sort_values("Datum")

        st.dataframe(df_plan)

        if remaining_days:
            st.warning(f"⚠️ Noch nicht verteilte Tage: {len(remaining_days)}")
        else:
            st.success("✅ Alle Tage wurden verteilt!")

        if not df_plan.empty:
            csv = df_plan.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Plan als CSV herunterladen", csv, "dienstplan.csv", "text/csv")
else:
    st.info("Bitte gib die Elternliste ein, um zu starten.")
