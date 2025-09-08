import streamlit as st
import requests
import time

# ==============================================================================
# --- PAGE CONFIGURATION ---
# ==============================================================================

st.set_page_config(
    page_title="LOGIA Demo",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for enhanced styling
st.markdown("""
<style>
    /* Main title styling */
    .main-title {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 3.5rem;
        font-weight: 800;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    
    .subtitle {
        text-align: center;
        color: #666;
        font-size: 1.2rem;
        margin-bottom: 2rem;
        font-style: italic;
    }
    
    /* Section headers */
    .section-header {
        color: #2c3e50;
        border-bottom: 3px solid #3498db;
        padding-bottom: 0.5rem;
        margin: 2rem 0 1rem 0;
    }
    
    /* Button styling */
    .stButton > button {
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 25px;
        padding: 0.6rem 2rem;
        font-weight: 600;
        transition: all 0.3s ease;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
    }
    
    /* Alert styling */
    .high-alert {
        background: linear-gradient(90deg, #ff6b6b, #ee5a24);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
        animation: pulse 2s infinite;
    }
    
    .safe-alert {
        background: linear-gradient(90deg, #55a3ff, #003d82);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        font-weight: bold;
    }
    
    @keyframes pulse {
        0% { opacity: 1; }
        50% { opacity: 0.7; }
        100% { opacity: 1; }
    }
    
    /* Card styling */
    .feature-card {
        background: white;
        padding: 2rem;
        border-radius: 15px;
        box-shadow: 0 10px 30px rgba(0,0,0,0.1);
        border: 1px solid #e0e0e0;
        margin: 1rem 0;
        transition: all 0.3s ease;
    }
    
    .feature-card:hover {
        transform: translateY(-5px);
        box-shadow: 0 15px 40px rgba(0,0,0,0.15);
    }
    
    /* Status indicators */
    .status-online {
        color: #27ae60;
        font-weight: bold;
    }
    
    .status-offline {
        color: #e74c3c;
        font-weight: bold;
    }
    
    .status-warning {
        color: #f39c12;
        font-weight: bold;
    }
    
    /* Info boxes */
    .info-box {
        background: linear-gradient(135deg, #74b9ff, #0984e3);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        margin: 1rem 0;
    }
    
    /* Metrics styling */
    .metric-container {
        background: #f8f9fa;
        padding: 1.5rem;
        border-radius: 10px;
        text-align: center;
        border-left: 4px solid #667eea;
    }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# --- HELPER FUNCTIONS ---
# ==============================================================================

def analyze_safety_audio(audio_bytes: bytes, filename: str):
    try:
        files = {"audio": (filename, audio_bytes, "audio/wav")}
        response = requests.post("http://localhost:8000/process-audio", files=files, timeout=30)
        return response.json()
    except Exception as e:
        return {"error": f"Failed to connect to Host for safety analysis: {e}"}

def resolve_disruption_with_router(text_scenario: str):
    try:
        response = requests.post("http://localhost:8000/resolve-disruption", json={"scenario": text_scenario}, timeout=60)
        return response.json()
    except Exception as e:
        return {"error": f"Failed to connect to Host for routing: {e}"}

def check_system_status():
    try:
        response = requests.get("http://localhost:8000/status", timeout=3)
        response.raise_for_status()
        return True, response.json()
    except requests.exceptions.RequestException:
        return False, None

# ==============================================================================
# --- MAIN APPLICATION ---
# ==============================================================================

# Header Section
st.markdown('<h1 class="main-title">🤖 LOGIA</h1>', unsafe_allow_html=True)
st.markdown('<p class="subtitle">AI-Powered Disruption Coordination & Safety Management System</p>', unsafe_allow_html=True)

# System Status Banner
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    status_container = st.container()
    system_online, status_data = check_system_status()
    
    if system_online:
        st.success("🟢 **System Status: ONLINE** | All systems operational")
    else:
        st.error("🔴 **System Status: OFFLINE** | Please check MCP Host connection")

st.markdown("---")

# Main Content Area
col_left, col_right = st.columns([1, 1], gap="large")

# Left Column - Disruption Resolver
with col_left:
    st.markdown("### 🧠 AI Disruption Resolver")
    
    with st.container():
        st.markdown("""
        <div class="info-box">
            <strong>🎯 Smart Problem Solving</strong><br>
            Describe any logistics challenge and let our AI coordinator find the optimal solution
        </div>
        """, unsafe_allow_html=True)
        
        scenario = st.text_area(
            "Describe your situation:",
            height=120,
            placeholder="e.g., 'My food delivery is 40 minutes late and I have a meeting' or 'The barber shop is closed, need alternative nearby'",
            help="Be as specific as possible for better AI assistance"
        )
        
        col_btn1, col_btn2 = st.columns([2, 1])
        with col_btn1:
            resolve_button = st.button("🚀 Get AI Solution", use_container_width=True, type="primary")
        with col_btn2:
            if st.button("🗑️ Clear", use_container_width=True):
                st.rerun()
        
        if resolve_button:
            if scenario:
                with st.spinner("🔍 AI Coordinator analyzing scenario..."):
                    time.sleep(0.5)  # Visual feedback
                    st.session_state.result = resolve_disruption_with_router(scenario)
                    st.session_state.result_type = "disruption"
            else:
                st.warning("⚠️ Please describe your situation first!")

# Right Column - Safety Alert System
with col_right:
    st.markdown("### 🛡️ Women's Safety Alert System")
    
    with st.container():
        st.markdown("""
        <div class="info-box">
            <strong>🚨 Real-time Threat Detection</strong><br>
            Upload audio files for immediate safety threat analysis using AI
        </div>
        """, unsafe_allow_html=True)
        
        uploaded_file = st.file_uploader(
            "Choose audio file for analysis:",
            type=['wav', 'mp3'],
            help="Supported formats: WAV, MP3. Max file size: 10MB"
        )
        
        if uploaded_file:
            # File info
            file_size = len(uploaded_file.getvalue()) / 1024  # KB
            st.info(f"📁 **File:** {uploaded_file.name} ({file_size:.1f} KB)")
            
            col_analyze, col_clear = st.columns([2, 1])
            with col_analyze:
                analyze_button = st.button("🔍 Analyze for Threats", use_container_width=True, type="primary")
            with col_clear:
                if st.button("❌ Remove File", use_container_width=True):
                    st.rerun()
            
            if analyze_button:
                with st.spinner("🛡️ Analyzing audio for safety threats..."):
                    time.sleep(0.5)  # Visual feedback
                    st.session_state.result = analyze_safety_audio(uploaded_file.getvalue(), uploaded_file.name)
                    st.session_state.result_type = "safety"

# Results Section
if 'result' in st.session_state:
    st.markdown("---")
    st.markdown("### 📊 Analysis Results")
    
    result = st.session_state.result
    result_type = st.session_state.get('result_type', 'unknown')
    
    if "error" in result:
        st.error(f"❌ **Error:** {result.get('detail', result.get('error'))}")
        st.info("💡 **Troubleshooting:** Make sure the MCP Host server is running on port 8000")
    
    elif result_type == "disruption" and "router_reasoning" in result:
        # Disruption Resolution Results
        col_reasoning, col_solution = st.columns([1, 1])
        
        with col_reasoning:
            with st.container():
                st.markdown("#### 🧠 AI Reasoning Process")
                st.code(result.get("router_reasoning", "No reasoning available"), language="text")
        
        with col_solution:
            with st.container():
                st.markdown("#### ✅ Recommended Solution")
                specialist_result = result.get("specialist_result", {})
                if "error" in specialist_result:
                 st.error(specialist_result["error"])
                else:
                # Extract and display the final text answer using st.markdown
                 final_answer = specialist_result.get("text", "No final answer provided by the agent.")
                 st.markdown(final_answer)
    
    elif result_type == "safety":
        # Safety Analysis Results
        alert_level = result.get("alert_level", "UNKNOWN")
        recognized_text = result.get("recognized_text", "No text recognized")
        
        # Alert Banner
        if alert_level == "HIGH":
            st.markdown("""
            <div class="high-alert">
                🚨 HIGH THREAT DETECTED 🚨<br>
                Immediate attention required!
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="safe-alert">
                ✅ SAFE - No threats detected
            </div>
            """, unsafe_allow_html=True)
        
        # Detailed Results
        col_text, col_details = st.columns([1, 1])
        
        with col_text:
            st.markdown("#### 📝 Recognized Speech")
            st.code(f'"{recognized_text}"', language=None)
        
        with col_details:
            st.markdown("#### 📈 Analysis Details")
            with st.expander("View complete analysis", expanded=True):
                st.json(result)

# ==============================================================================
# --- SIDEBAR ---
# ==============================================================================

with st.sidebar:
    st.markdown("### 🔧 System Dashboard")
    
    # System Status
    system_online, status_data = check_system_status()
    
    if system_online:
        st.markdown('<p class="status-online">🟢 MCP Host: ONLINE</p>', unsafe_allow_html=True)
        
        # Check individual agents
        registered_tools = status_data.get("registered_tools", []) if status_data else []
        
        if "safety/analyzeAudio" in registered_tools:
            st.markdown('<p class="status-online">🟢 Safety Agent: CONNECTED</p>', unsafe_allow_html=True)
        else:
            st.markdown('<p class="status-warning">🟡 Safety Agent: DISCONNECTED</p>', unsafe_allow_html=True)
        
        # Additional system info
        if status_data:
            st.markdown("#### System Metrics")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Tools", len(registered_tools))
            with col2:
                st.metric("Status", "Online", delta="Healthy")
    else:
        st.markdown('<p class="status-offline">🔴 MCP Host: OFFLINE</p>', unsafe_allow_html=True)
        st.markdown('<p class="status-offline">🔴 Safety Agent: UNAVAILABLE</p>', unsafe_allow_html=True)
        
        st.warning("⚠️ **Connection Issues**\n\nPlease ensure the MCP Host is running:\n``````")
    
    st.markdown("---")
    
    # Quick Actions
    st.markdown("### ⚡ Quick Actions")
    if st.button("🔄 Refresh Status", use_container_width=True):
        st.rerun()
    
    if st.button("🗑️ Clear Results", use_container_width=True):
        if 'result' in st.session_state:
            del st.session_state.result
        if 'result_type' in st.session_state:
            del st.session_state.result_type
        st.rerun()
    
    st.markdown("---")
    
    # About Section
    st.markdown("### ℹ️ About LOGIA")
    st.markdown("""
    **LOGIA** is an AI-powered coordination system that:
    
    - 🧠 Solves logistics disruptions intelligently
    - 🛡️ Provides real-time safety monitoring  
    - 🤖 Uses modular agent architecture
    - ⚡ Delivers instant responses
    
    Built with **Python**, **Streamlit**, and **FastAPI**.
    """)
    
    # Footer
    st.markdown("---")
    st.markdown("*Version 1.0 | Built for Demo*")
