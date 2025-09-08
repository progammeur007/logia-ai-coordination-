import uvicorn
import httpx
import base64
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from contextlib import asynccontextmanager
from typing import Dict, Any
from datetime import datetime
import uvicorn
import httpx
import base64
import os  # Import the os module
from dotenv import load_dotenv  # Import the load_dotenv function
from twilio.rest import Client
import json

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import Tool, create_react_agent, AgentExecutor
from langchain_core.prompts import PromptTemplate
from langchain_core.pydantic_v1 import BaseModel, Field

load_dotenv()
# ==============================================================================
# 1. CONFIGURATION
# ==============================================================================
# All your agent (MCP Server) addresses will go here.
SAFETY_SERVER_URL = "http://localhost:8001"


# ==============================================================================
# 2. GLOBAL STATE FOR THE HOST
# ==============================================================================
# This registry will store all tools discovered from all connected servers.
# It maps a tool name to the client that can handle it.
TOOL_REGISTRY: Dict[str, 'MCPClient'] = {}
safety_agent_client = None
router_agent_executor = None

# In-memory status tracking for the dashboard.
current_status = {
    "last_recognized_text": "",
    "threat_level": "SAFE",
    "last_update": None,
    "active_alerts": 0
}


# ==============================================================================
# 3. MCP HELPER CLASS
# ==============================================================================
# A small helper to manage communication with a single agent.
class MCPClient:
    def __init__(self, server_name: str, server_address: str):
        self.name = server_name
        self.address = server_address
        self.client = httpx.AsyncClient(base_url=self.address, timeout=90.0)
        self.tools = []

    async def _send_request(self, method: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}}
        try:
            response = await self.client.post("/", json=payload)
            response.raise_for_status()
            return response.json()
        except httpx.RequestError as e:
            print(f"❌ Could not communicate with {self.name}: {e}")
            return {"error": {"message": str(e)}}

    async def initialize(self) -> bool:
        print(f"🤝 Initializing with {self.name}...")
        response = await self._send_request("initialize", {"clientInfo": {"name": "LOGIA Host"}})
        if "result" in response and "capabilities" in response["result"]:
            print(f"✅ Initialization successful with {self.name}.")
            return True
        print(f"🔥 Initialization failed with {self.name}.")
        return False

    async def list_tools(self):
        print(f"🔎 Discovering tools from {self.name}...")
        response = await self._send_request("tools/list")
        if "result" in response and "tools" in response["result"]:
            self.tools = response["result"]["tools"]
            print(f"  - Found {len(self.tools)} tools from {self.name}.")
            return self.tools
        return []

    async def call_tool(self, tool_name: str, arguments: Dict) -> Dict[str, Any]:
        print(f"🚀 Calling tool '{tool_name}' on {self.name}...")
        return await self._send_request("tools/call", {"name": tool_name, "arguments": arguments})
    
def create_router_agent():
    """
    Initializes a highly efficient LLM router that uses structured output
    to make a single, decisive choice without looping.
    """
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key: raise ValueError("GEMINI_API_KEY not found in .env file.")
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash-latest", google_api_key=api_key, temperature=0.0, timeout=45)
        llm.invoke("test")
    except Exception as e:
        print("="*60); print("🔥🔥🔥 FAILED TO INITIALIZE GEMINI LLM 🔥🔥🔥"); print(f"Error: {e}"); print("="*60)
        return None

    # 1. Define the desired output structure using Pydantic.
    class RouterChoice(BaseModel):
        agent_name: str = Field(description="The name of the agent to route to. Must be one of ['safety_agent', 'food_delay_agent', 'cab_rerouting_agent'].")

    # 2. Bind this structure to the LLM to force its output into our desired format.
    structured_llm = llm.with_structured_output(RouterChoice)

    # 3. Create a much simpler prompt for direct classification.
    prompt_template = """You are an expert logistics dispatcher. Analyze the user's problem and decide which department is best suited to handle it. The available departments are 'safety_agent', 'food_delay_agent', and 'cab_rerouting_agent'.

    User's Problem: "{input}"
    
    Based on the problem, choose the single most appropriate department.
    """
    prompt = PromptTemplate.from_template(prompt_template)

    # 4. Create the final, simple chain. This is not an agent, just a direct sequence.
    return prompt | structured_llm



# ==============================================================================
# 4. APPLICATION LIFESPAN (STARTUP/SHUTDOWN)
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 LOGIA MCP Host is starting up...")
    global safety_agent_client, router_agent_executor
    
    # On startup, create a client for our Safety Agent
    safety_agent_client = MCPClient("SafetyServer", SAFETY_SERVER_URL)
    
    # Perform the MCP handshake and discover tools
    if await safety_agent_client.initialize():
        tools = await safety_agent_client.list_tools()
        for tool in tools:
            TOOL_REGISTRY[tool['name']] = safety_agent_client
            print(f"  - Registered tool '{tool['name']}'")

    print("\n--- Connecting to Specialist Agents listed in servers.json ---")
    try:
        with open("servers.json", 'r') as f:
            server_configs = json.load(f)
    except FileNotFoundError:
        print("🔥 servers.json not found. No specialist agents will be connected.")
        server_configs = []

    for config in server_configs:
        if not config.get("enabled"):
            continue

        name = config["name"]
        address = config["address"]
        
        # Create a client for each agent in the config file
        client = MCPClient(name, address)
        
        # Perform the MCP handshake and discover its tools
        if await client.initialize():
            tools = await client.list_tools()
            for tool in tools:
                tool_name = tool.get('name')
                if tool_name:
                    TOOL_REGISTRY[tool_name] = client
                    print(f"  - Registered tool '{tool_name}' from {name}")
    print("----------------------------------------------------------")
    # --- END OF NEW LOGIC ---
     # --- NEW: Initialize the Router Agent on startup ---
    print("\n🧠 Initializing Router Agent... (This may take a few seconds)")
    router_agent_executor = create_router_agent()
    if router_agent_executor:
        print("✅ Router Agent is ready and online.\n")
    else:
        print("❌ Router Agent failed to initialize. Check Gemini API key and logs.\n")
        

    yield
    print("👋 LOGIA MCP Host is shutting down.")


# ==============================================================================
# 5. FASTAPI APPLICATION AND ENDPOINTS
# ==============================================================================
app = FastAPI(title="LOGIA MCP Host (Single File)", lifespan=lifespan)

@app.get("/")
async def root():
    return {
        "service": "LOGIA MCP Host",
        "status": "running",
        "registered_tools": list(TOOL_REGISTRY.keys())
    }

@app.get("/status")
async def get_status():
    """Provides the live dashboard status of the Host."""
    return {
        "host_dashboard": {
            "current_threat_level": current_status["threat_level"],
            "last_recognized_text": current_status["last_recognized_text"],
            "active_alerts_today": current_status["active_alerts"],
            "last_status_update": current_status["last_update"]
        },
        "registered_tools": list(TOOL_REGISTRY.keys())
    }

@app.post("/process-audio")
async def process_audio(audio: UploadFile = File(...)):
    """
    Receives audio, calls the Safety Server's tool, and takes action.
    """
    tool_name = "safety/analyzeAudio"
    
    client = TOOL_REGISTRY.get(tool_name)
    if not client:
        raise HTTPException(status_code=501, detail=f"No server found that provides the tool '{tool_name}'")

    audio_bytes = await audio.read()
    audio_base64 = base64.b64encode(audio_bytes).decode('utf-8')
    arguments = {
        "audio_data": audio_base64,
        "encoding": "base64",
        "file_format": audio.content_type
    }

    result = await client.call_tool(tool_name, arguments)

    if "error" in result:
        raise HTTPException(status_code=500, detail=f"Error from {client.name}: {result['error']['message']}")
    
    # --- ACTION LOGIC STARTS HERE ---
    final_result_data = {}
    if result.get("result", {}).get("content"):
        final_result_data = result["result"]["content"][0].get("data", {})

    if final_result_data:
        alert_level = final_result_data.get("alert_level", "UNKNOWN")
        recognized_text = final_result_data.get("recognized_text", "")
        
        current_status["threat_level"] = alert_level
        current_status["last_recognized_text"] = recognized_text
        current_status["last_update"] = datetime.now().isoformat()
        
        print(f"✅ Analysis complete. Text: '{recognized_text}' | Level: {alert_level}")

        if alert_level == "HIGH":
            current_status["active_alerts"] += 1
            print("="*40)
            print(f"🚨🚨 HIGH THREAT ALERT DETECTED! 🚨🚨")
            print(f"   Recognized Text: '{recognized_text}'")
            print(f"   Matched Words: {final_result_data.get('matched_words')}")
            print("="*40)

              # ==========================================================
            # SECURE PROTOTYPE ACTION: SEND AN SMS WITH TWILIO
            # ==========================================================
            try:
                # Read credentials securely from the environment
                account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
                auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
                twilio_phone = os.environ.get("TWilio_PHONE_NUMBER")
                your_phone = os.environ.get("YOUR_PHONE_NUMBER")

                # Check if the variables were loaded correctly
                if not all([account_sid, auth_token, twilio_phone, your_phone]):
                    print(" T_WARNING: Twilio environment variables not set. Skipping SMS alert.")
                else:
                    client = Client(account_sid, auth_token)
                    message_body = (
                        f"CRITICAL SAFETY ALERT from LOGIA!\n"
                        f"Threat Level: HIGH\n"
                        f"Detected Phrase: '{recognized_text}'\n"
                        f"Location: [Prototype Location]"
                    )
                    
                    message = client.messages.create(
                        body=message_body,
                        from_=twilio_phone,
                        to=your_phone
                    )
                    print(f"✅ Successfully sent SMS alert via Twilio! SID: {message.sid}")

            except Exception as e:
                print(f"🔥 FAILED to send SMS alert: {e}")
    # --- ACTION LOGIC ENDS HERE ---
        
    return final_result_data



@app.post("/resolve-disruption")
async def resolve_disruption(scenario: str = Body(..., embed=True)):
    if not router_agent_executor:
        raise HTTPException(status_code=503, detail="Router Agent is initializing or failed. Please try again.")

    try:
        print(f"🧠 Router received scenario: '{scenario}'. Invoking Gemini for a direct choice...")
        router_response_object = await router_agent_executor.ainvoke({"input": scenario})
        chosen_agent_name = router_response_object.agent_name

        router_reasoning = f"Input: '{scenario}'\nLLM Analysis: The user's problem is about '{chosen_agent_name}'.\nDecision: Routing to the {chosen_agent_name}."
        print(f"✅ Router decision: {chosen_agent_name}")

        specialist_result = {}

        
        if "food_delay_agent" in chosen_agent_name:
            client = TOOL_REGISTRY.get("food/resolveDelay")
            if client:
                # Call the real agent and get its response
                specialist_response = await client.call_tool("food/resolveDelay", {"scenario": scenario})
                # Extract the final answer from the agent's response
                specialist_result = specialist_response.get("result", {}).get("content", [{}])[0]
            else:
                specialist_result = {"error": "Food Delay Agent is not connected. Check servers.json and agent status."}

        elif "cab_rerouting_agent" in chosen_agent_name:
            client = TOOL_REGISTRY.get("cab/rerouteRequest")
            if client:
             specialist_response = await client.call_tool("cab/rerouteRequest", {"scenario": scenario})
             specialist_result = specialist_response.get("result", {}).get("content", [{}])[0]
            else:
             specialist_result = {"error": "Cab Rerouting Agent is not connected."}

        elif "safety_agent" in chosen_agent_name:
            specialist_result = {"action": "Routing to Safety Agent.", "details": "This requires audio input via the Safety Alert section."}

    except Exception as e:
        print(f"🔥🔥🔥 LLM ROUTING FAILED 🔥🔥🔥\nError: {e}")
        raise HTTPException(status_code=500, detail=f"LLM Routing Error: {e}")

    return {
        "router_reasoning": router_reasoning,
        "specialist_result": specialist_result
    }



# ==============================================================================
# 6. RUN THE SERVER
# ==============================================================================
if __name__ == "__main__":
    print("Starting LOGIA MCP Host...")
    uvicorn.run(app, host="localhost", port=8000)