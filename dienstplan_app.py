import streamlit as st
import pandas as pd
import datetime
import random

st.set_page_config(page_title="KITA Dienstplan Tool")
st.title("📅 KITA Dienstplan Generator")

# Eingaben
st.sidebar.header("🔧 Einstellungen")
start_date = st.sidebar.date_input("Startdatum", datetime.date.today())
weeks = st.sidebar.number_input("Zeitraum in Wochen", min_value=1, max_value=52, value=7)
parents_input = st.sidebar.text_area("Elternliste (ein Name pro Zeile)")

def generate_workdays(start, weeks):
    days = pd.date_range(start=start, periods=weeks * 7)
    weekdays = days[days.weekday < 5]  # Nur Mo–Fr
    return list(weekdays)

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

        for idx, parent in enumerate(parents):
            st.markdown(f"### 🧑‍🍼 {parent}")
            n_days = days_per_parent + (1 if idx < rest_days else 0)
            preselected = selections.get(parent, [])
            options = sorted(remaining_days.union(preselected))
            selected = st.multiselect(f"Wähle {n_days} Tage für {parent}",
                                      options,
                                      default=preselected,
                                      key=f"sel_{parent}")
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

        df_plan = pd.DataFrame(table).sort_values("Datum")
        st.dataframe(df_plan)

        if remaining_days:
            st.warning(f"⚠️ Noch nicht verteilte Tage: {len(remaining_days)}")
        else:
            st.success("✅ Alle Tage wurden verteilt!")

        csv = df_plan.to_csv(index=False).encode('utf-8')
        st.download_button("📥 Plan als CSV herunterladen", csv, "dienstplan.csv", "text/csv")
else:
    st.info("Bitte gib die Elternliste ein, um zu starten.")
