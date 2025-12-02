import streamlit as st
import requests
import time

API = "http://127.0.0.1:5000"

st.set_page_config(page_title="Traffic Dashboard", layout="wide")

st.title("🚦 Smart Traffic Control System Dashboard")


# -----------------------------
# تحديث البيانات كل ثانية
# -----------------------------
def get_data():
    try:
        return requests.get(f"{API}/get").json()
    except:
        return None


# -----------------------------
# UI
# -----------------------------
placeholder = st.empty()

while True:
    data = get_data()

    if data is None:
        st.error("❌ Cannot connect to backend API")
        time.sleep(1)
        continue

    with placeholder.container():

        st.subheader("📊 Lane Densities")
        st.write(data["density"])

        st.subheader("📡 Beacon Status")
        st.write("ON" if data["beacon"] else "OFF")

        st.subheader("⏱ Time Response")
        st.write(f"{data['time_response']:.2f} sec")

        st.subheader("🟢 Next Green Allocation")
        st.write(data["next_green"])

        st.subheader("🚑 Priority Lane Selection (Beacon Mode)")
        lane = st.selectbox("Select Lane (0–3)", [0,1,2,3])

        if st.button("Send Priority Lane"):
            try:
                requests.post(f"{API}/set_lane", json={"lane": lane})
                st.success("Lane sent successfully!")
            except:
                st.error("Failed to send lane.")

    time.sleep(1)
