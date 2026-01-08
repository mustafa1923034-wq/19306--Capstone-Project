import streamlit as st
import requests
import time
import plotly.graph_objects as go
from config import *
from datetime import datetime

st.set_page_config(
    page_title="🚦 Intelligent Traffic Control Dashboard",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .status-card {
        padding: 15px;
        border-radius: 10px;
        margin: 10px 0;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        transition: all 0.3s ease;
    }
    .online { 
        background: linear-gradient(135deg, #d4edda 0%, #c3e6cb 100%);
        border-left: 5px solid #28a745;
    }
    .offline { 
        background: linear-gradient(135deg, #f8d7da 0%, #f5c6cb 100%);
        border-left: 5px solid #dc3545;
    }
    .traffic-light {
        display: inline-flex;
        flex-direction: column;
        align-items: center;
        gap: 5px;
        margin: 10px 0;
    }
    .light {
        width: 30px;
        height: 30px;
        border-radius: 50%;
        border: 3px solid #333;
        box-shadow: inset 0 0 10px rgba(0,0,0,0.2);
    }
    .green.active { background-color: #28a745; box-shadow: 0 0 20px #28a745; }
    .yellow.active { background-color: #ffc107; box-shadow: 0 0 20px #ffc107; }
    .red.active { background-color: #dc3545; box-shadow: 0 0 20px #dc3545; }
    .light:not(.active) { background-color: #6c757d; opacity: 0.3; }
    .metric-card {
        background: white;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        text-align: center;
    }
    .metric-value {
        font-size: 24px;
        font-weight: bold;
        color: #007bff;
    }
    .metric-label {
        font-size: 14px;
        color: #6c757d;
    }
    .beacon-active {
        animation: pulse 2s infinite;
        background: linear-gradient(135deg, #fff3cd 0%, #ffeaa7 100%);
        border-left: 5px solid #ffc107;
    }
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
    }
</style>
""", unsafe_allow_html=True)

def check_backend_status():
    try:
        response = requests.get(f"{BACKEND_URL}/status", timeout=2)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def get_traffic_data():
    try:
        response = requests.get(f"{BACKEND_URL}/get", timeout=2)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def get_system_config():
    try:
        response = requests.get(f"{BACKEND_URL}/config", timeout=2)
        if response.status_code == 200:
            return response.json()
    except:
        pass
    return None

def set_priority_lane(lane):
    try:
        response = requests.post(
            f"{BACKEND_URL}/set_lane",
            json={"lane": lane},
            timeout=2
        )
        if response.status_code == 200:
            return True, response.json()
    except Exception as e:
        return False, str(e)
    return False, "Unknown error"

def clear_beacon():
    try:
        response = requests.post(f"{BACKEND_URL}/clear_beacon", timeout=2)
        if response.status_code == 200:
            return True
    except:
        pass
    return False

def extend_beacon():
    try:
        response = requests.post(f"{BACKEND_URL}/extend_beacon", timeout=2)
        if response.status_code == 200:
            return True, response.json()
    except Exception as e:
        return False, str(e)
    return False, "Unknown error"

def get_phase_name(phase_idx):
    phases = ["🟢 GREEN", "🟡 YELLOW", "🔴 RED", "🟡 YELLOW"]
    return phases[phase_idx] if 0 <= phase_idx < len(phases) else "UNKNOWN"

with st.sidebar:
    st.title("⚙️ System Control")
    
    status = check_backend_status()
    if status:
        st.success("✅ Backend Connected")
        esp_status = "✅ Connected" if status.get("esp_connected") else "❌ Disconnected"
        st.info(f"ESP32: {esp_status}")
        
        if status.get("esp_connected"):
            time_since = status.get("time_since_update", 0)
            st.caption(f"Last update: {time_since:.1f} seconds ago")
    else:
        st.error("❌ Backend Offline")
    
    st.divider()
    
    st.subheader("🔄 Auto Refresh")
    auto_refresh = st.checkbox("Enable", value=True)
    refresh_rate = st.slider("Rate (seconds)", 1, 10, 2)
    
    st.divider()
    
    config = get_system_config()
    if config:
        st.subheader("📊 System Info")
        st.caption(f"Cycle: {config['cycle_config']['total']}s")
        st.caption(f"Yellow: {config['cycle_config']['yellow']}s")
        st.caption(f"Green: {config['cycle_config']['green_min']}-{config['cycle_config']['green_max']}s")
    
    st.divider()
    
    st.subheader("🛠️ Manual Control")
    if st.button("🔄 Force Refresh", use_container_width=True):
        st.rerun()

st.title("🚦 Intelligent Traffic Control System")
st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Backend Status", "Online" if status else "Offline")
with col2:
    esp_connected = status.get("esp_connected") if status else False
    st.metric("ESP32 Status", "Connected" if esp_connected else "Disconnected")
with col3:
    if status:
        latency = status.get("current_state", {}).get("latency_ms", 0)
        st.metric("Latency", f"{latency} ms")
with col4:
    cycle_progress = 50
    if status and esp_connected:
        data = get_traffic_data()
        if data and "cycle_progress" in data:  # ✅ fixed
            progress_list = data["cycle_progress"]
            if isinstance(progress_list, list) and len(progress_list) == 4:
                cycle_progress = int(sum(progress_list) / 4)
    st.metric("Cycle Progress", f"{cycle_progress}%")

st.subheader("🚦 Traffic Light Status")

if not status or not esp_connected:
    st.warning("⚠️ ESP32 not connected. Displaying simulated data.")
    for i in range(4):
        col1, col2, col3, col4 = st.columns(4)
        with [col1, col2, col3, col4][i]:
            st.markdown(f"### {JUNCTION_MAPPING[i]['name']}")
            st.markdown("""
            <div class='traffic-light'>
                <div class='light red active'></div>
                <div class='light yellow'></div>
                <div class='light green'></div>
            </div>
            """, unsafe_allow_html=True)
            st.write("**Status:** 🔴 RED")
            st.write("**Density:** 0 vehicles")
            st.write("**Timing:** 30s green | 15s red")
else:
    data = get_traffic_data()
    if data:
        cols = st.columns(4)
        
        for i in range(4):
            with cols[i]:
                junction_name = JUNCTION_MAPPING[i]["name"]
                phase_idx = data["current_phase_idx"][i]
                phase_name = get_phase_name(phase_idx)
                
                light_html = f"""
                <div class='traffic-light'>
                    <div class='light red {'active' if phase_idx == 2 else ''}'></div>
                    <div class='light yellow {'active' if phase_idx in [1, 3] else ''}'></div>
                    <div class='light green {'active' if phase_idx == 0 else ''}'></div>
                </div>
                """
                st.markdown(f"### {junction_name}")
                st.markdown(light_html, unsafe_allow_html=True)
                
                st.write(f"**Status:** {phase_name}")
                st.write(f"**Density Before:** {data['density'][i]} vehicles")
                st.write(f"**Density After:** {data['density_after'][i]} vehicles")
                
                if i < len(data["current_times"]):
                    times = data["current_times"][i]
                    if len(times) >= 4:
                        st.write(f"**Green:** {times[0]}s | **Red:** {times[2]}s")

st.subheader("📊 Traffic Density")

if status and esp_connected and data:  # ✅ fixed
    fig = go.Figure()
    
    junctions = [JUNCTION_MAPPING[i]["name"] for i in range(4)]
    
    fig.add_trace(go.Bar(
        name='Before Light',
        x=junctions,
        y=data["density"],
        marker_color='#ff6b6b'
    ))
    
    fig.add_trace(go.Bar(
        name='After Light',
        x=junctions,
        y=data["density_after"],
        marker_color='#4ecdc4'
    ))
    
    fig.update_layout(
        title="Vehicle Counts at Junctions",
        barmode='group',
        xaxis_title="Junction",
        yaxis_title="Number of Vehicles",
        height=400,
        showlegend=True
    )
    
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No density data available. Connect ESP32 to see live traffic data.")

st.subheader("🚨 Emergency Vehicle Priority")

if status and esp_connected and data:  # ✅ fixed
    beacon_active = data.get("beacon", False)
    priority_lane = data.get("priority_lane")
    
    if beacon_active and priority_lane is not None:
        junction_name = JUNCTION_MAPPING.get(priority_lane, {}).get("name", f"Lane {priority_lane}")
        
        st.markdown(f"""
        <div class='status-card beacon-active'>
            <h3>⚠️ BEACON ACTIVE</h3>
            <p>Priority granted to <strong>{junction_name}</strong></p>
            <p>Maximum green time allocated for emergency vehicle passage</p>
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✖️ Cancel Priority", use_container_width=True, type="primary"):
                if clear_beacon():
                    st.success("✅ Priority cancelled")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error("❌ Failed to cancel priority")
        with col2:
            if st.button("⏱️ Extend Priority", use_container_width=True):
                success, result = extend_beacon()
                if success:
                    st.success("✅ Priority extended for 30 seconds")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ Failed: {result}")
    else:
        st.info("No active emergency priority. Use controls below to activate.")
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            lane_options = [
                f"{i} - {JUNCTION_MAPPING[i]['name']} ({JUNCTION_MAPPING[i]['in_edge']}→{JUNCTION_MAPPING[i]['out_edge']})"
                for i in range(4)
            ]
            selected_option = st.selectbox("Select Priority Junction", lane_options)
            selected_lane = int(selected_option.split(" - ")[0])
        
        with col2:
            if st.button(" ambulance Activate Priority", use_container_width=True, type="primary"):
                success, result = set_priority_lane(selected_lane)
                if success:
                    st.success(f"✅ Priority activated for {JUNCTION_MAPPING[selected_lane]['name']}")
                    time.sleep(0.5)
                    st.rerun()
                else:
                    st.error(f"❌ Failed: {result}")

st.subheader("⏱️ Cycle Timing")

if status and esp_connected and data:  # ✅ fixed
    timing_cols = st.columns(4)
    
    for i in range(4):
        with timing_cols[i]:
            if i < len(data.get("current_times", [])):
                times = data["current_times"][i]
                if len(times) >= 4:
                    st.markdown(f"""
                    <div class='metric-card'>
                        <div class='metric-label'>{JUNCTION_MAPPING[i]['name']}</div>
                        <div class='metric-value'>{times[0]}s</div>
                        <div class='metric-label'>Green Time</div>
                        <div class='metric-value'>{times[2]}s</div>
                        <div class='metric-label'>Red Time</div>
                    </div>
                    """, unsafe_allow_html=True)
    
    if "next_green" in data:  # ✅ fixed
        st.write("**Next Cycle Green Times:**", data["next_green"])
else:
    st.info("Connect ESP32 to see cycle timing information")

# Add sensor status
if status and esp_connected and data:  # ✅ fixed
    sensor_status = data.get("sensor_status", [True]*8)
    st.subheader("📡 Sensor Status")
    cols = st.columns(8)
    for i in range(8):
        with cols[i]:
            color = "🟢" if sensor_status[i] else "🔴"
            st.write(f"**Sensor {i}:** {color}")

# Use streamlit-autorefresh for smooth updates
try:
    from streamlit_autorefresh import st_autorefresh
    if auto_refresh:
        st_autorefresh(interval=refresh_rate * 1000, key="dashboard_refresh")
except ImportError:
    if auto_refresh:
        time.sleep(refresh_rate)
        st.rerun()