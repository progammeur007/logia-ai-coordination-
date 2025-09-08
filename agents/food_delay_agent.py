import os
import json
import uvicorn
import re
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from typing import List, Dict, Any

# --- LangChain and Gemini Imports ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain.tools import StructuredTool
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field
from twilio.rest import Client

# Load environment variables from the root .env file
load_dotenv()

# ==============================================================================
# 1. SIMULATED DATABASE AND TOOLS
# ==============================================================================
def load_system_data():
    """Loads the system_data.json file from the project's root directory."""
    try:
        script_dir = os.path.dirname(__file__)
        json_path = os.path.join(script_dir, "..", "system_data.json")
        with open(json_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print("🔥 system_data.json not found in the root directory!")
        return {}

def get_order_details(order_id: str) -> str:
    """Gets all details for a specific order ID, including the driver's current location."""
    print(f"--- TOOL CALLED: get_order_details ---")
    data = load_system_data()
    order = data.get("orders", {}).get(order_id)
    if not order:
        return f"Error: Order ID '{order_id}' not found."
    driver_id = order.get("driver_id")
    if driver_id:
        driver_details = data.get("drivers", {}).get(driver_id)
        if driver_details:
            order['driver_current_location'] = driver_details.get('current_location')
    return str(order)

def get_merchant_details(merchant_id: str) -> str:
    """Gets details for a specific merchant ID, like name, location, and prep time."""
    print(f"--- TOOL CALLED: get_merchant_details ---")
    data = load_system_data()
    merchant = data.get("restaurants", {}).get(merchant_id)
    if not merchant:
        return f"Error: Merchant ID '{merchant_id}' not found."
    return str(merchant)
    
def find_nearest_pending_order(driver_location: int, current_merchant_id: str) -> str:
    """Finds the nearest available order for a driver, excluding the current merchant."""
    print(f"--- TOOL CALLED: find_nearest_pending_order ---")
    data = load_system_data()
    pending_orders = {oid: o for oid, o in data.get("orders", {}).items() if o.get("status") == "Awaiting Pickup"}
    if not pending_orders:
        return "No other pending orders available for rerouting."
    
    nearest_order_id = None
    min_distance = float('inf')

    for order_id, order in pending_orders.items():
        merchant_id = order.get("merchant_id")
        if merchant_id != current_merchant_id:
            merchant = data.get("restaurants", {}).get(merchant_id)
            if merchant:
                distance = abs(merchant.get("location", 0) - driver_location)
                if distance < min_distance:
                    min_distance = distance
                    nearest_order_id = order_id
    
    if nearest_order_id:
        new_merchant = data.get("restaurants", {}).get(pending_orders[nearest_order_id]['merchant_id'])
        return f"Found nearest pending order: {nearest_order_id} at {new_merchant.get('name')}, {min_distance} units away."
    
    return "No suitable nearby order could be found that is not at the current merchant."

def get_nearby_merchants(current_merchant_id: str) -> str:
    """Finds similar, nearby restaurants that are not overloaded to suggest to a customer."""
    print(f"--- TOOL CALLED: get_nearby_merchants ---")
    data = load_system_data()
    all_merchants = data.get("restaurants", {})
    
    current_merchant = all_merchants.get(current_merchant_id)
    if not current_merchant:
        return "Error: Could not find the current merchant to search near."
    current_location = current_merchant.get("location")

    alternatives = []
    for merchant_id, merchant in all_merchants.items():
        if merchant_id != current_merchant_id and merchant.get("status") == "Normal":
            alternatives.append(merchant)
    
    alternatives.sort(key=lambda x: abs(x.get("location", 0) - current_location))
    
    if not alternatives:
        return "No suitable, non-overloaded alternative merchants found nearby."
    
    return str([{"name": m.get("name"), "prep_time": m.get("prep_time_mins")} for m in alternatives[:2]])

def notify_via_twilio(message: str) -> str:
    """Sends a notification message via Twilio SMS."""
    print(f"--- TOOL CALLED: notify_via_twilio ---")
    try:
        account_sid, auth_token, twilio_phone, your_phone = (os.environ.get(k) for k in ["TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER", "YOUR_PHONE_NUMBER"])
        if not all([account_sid, auth_token, twilio_phone, your_phone]):
            return "Twilio credentials are not fully configured."
        client = Client(account_sid, auth_token)
        sms = client.messages.create(body=f"[LOGIA Alert] {message}", from_=twilio_phone, to=your_phone)
        return "Notification successfully sent."
    except Exception as e:
        return f"Error sending notification: {e}"

# --- Pydantic models for structured tool inputs ---
class GetOrderInput(BaseModel):
    order_id: str = Field(description="The ID of the order to get details for.")
class GetMerchantInput(BaseModel):
    merchant_id: str = Field(description="The ID of the merchant to get details for.")
class FindOrderInput(BaseModel):
    driver_location: int = Field(description="The current linear coordinate of the driver.")
    current_merchant_id: str = Field(description="The ID of the current merchant to exclude from the search.")
class GetNearbyInput(BaseModel):
    current_merchant_id: str = Field(description="The ID of the current merchant to search near.")
class NotifyInput(BaseModel):
    message: str = Field(description="The message to send.")

# ==============================================================================
# 2. SETUP THE RELIABLE LANGCHAIN AGENT
# ==============================================================================
class LangChainFoodAgent:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash-latest", google_api_key=os.environ.get("GEMINI_API_KEY"), temperature=0.0)
        
        # --- Using StructuredTool for robust, multi-argument tool calls ---
        tools = [
            StructuredTool.from_function(func=get_order_details, name="get_order_details", args_schema=GetOrderInput),
            StructuredTool.from_function(func=get_merchant_details, name="get_merchant_details", args_schema=GetMerchantInput),
            StructuredTool.from_function(func=find_nearest_pending_order, name="find_nearest_pending_order", args_schema=FindOrderInput),
            StructuredTool.from_function(func=get_nearby_merchants, name="get_nearby_merchants", args_schema=GetNearbyInput),
            StructuredTool.from_function(func=notify_via_twilio, name="notify_via_twilio", args_schema=NotifyInput),
        ]

        prompt_template = """You are LOGIA, an autonomous logistics coordinator. Your goal is to proactively resolve delivery disruptions by following a strict, mandatory plan.

        You have access to the following tools:
        {tools}

        You MUST respond in a JSON blob with an "action" and "action_input". Valid "action" values are "Final Answer" or one of [{tool_names}].

        **Your Mandatory Plan:**
        1.  FIRST, use `get_order_details` to get the `merchant_id` and driver's `driver_current_location`.
        2.  SECOND, use `get_merchant_details` with the `merchant_id`.
        3.  THIRD, analyze the prep time and apply the '40-minute rule':
            - **IF prep time > 40 mins (Critical Delay):**
                a. Use `find_nearest_pending_order` with the driver's location and current merchant ID.
                b. Use `get_nearby_merchants` with the current merchant ID.
                c. Use `notify_via_twilio` to inform the DRIVER of their new task. The message MUST be specific.
                d. Use `notify_via_twilio` to inform the CUSTOMER of the delay and include the alternative restaurants you found.
            - **IF prep time <= 40 mins (Minor Delay):**
                a. ONLY use `notify_via_twilio` to inform the CUSTOMER of the wait time.
        4.  FINALLY, provide a "Final Answer" summarizing all actions taken.

        The user's request is as follows:
        {input}
        
        {agent_scratchpad}
        """
        prompt = PromptTemplate.from_template(prompt_template)
        agent = create_structured_chat_agent(self.llm, tools, prompt)
        self.agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True, handle_parsing_errors=True)

    async def run(self, scenario: str) -> str:
        try:
            response = await self.agent_executor.ainvoke({"input": scenario})
            return response.get("output", "No output generated.")
        except Exception as e:
            return f"🔥🔥🔥 AGENT EXECUTION FAILED 🔥🔥🔥\nError: {e}"

# ==============================================================================
# 3. CREATE THE MCP SERVER (The Agent's "Body")
# ==============================================================================
class FoodDelayMCP_Server:
    def __init__(self):
        self.agent = LangChainFoodAgent()
        self.tool_definition = [{"name": "food/resolveDelay", "title": "Resolve Food Delivery Delay"}]
    def mcp_initialize(self, params): return {"capabilities": {"tools": {}}}
    def mcp_tools_list(self, params): return {"tools": self.tool_definition}
    async def mcp_tools_call(self, params):
        scenario = params.get("arguments", {}).get("scenario")
        if not scenario: return {"error": {"message": "Scenario is required."}}
        result = await self.agent.run(scenario)
        return {"content": [{"type": "text", "text": result}]}
    async def handle_rpc_request(self, request: Request):
        body = await request.json()
        method, params, request_id = body.get("method"), body.get("params"), body.get("id")
        result = {"error": {"message": "Method not found"}}
        if method == "initialize": result = self.mcp_initialize(params)
        elif method == "tools/list": result = self.mcp_tools_list(params)
        elif method == "tools/call": result = await self.mcp_tools_call(params)
        return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})

# --- Main Application Setup ---
if __name__ == "__main__":
    print("🍔 LOGIA Food Delay Agent (MCP Server) Starting...")
    mcp_server = FoodDelayMCP_Server()
    app = FastAPI(title="LOGIA Food Delay Agent")
    @app.post("/")
    async def rpc_endpoint(request: Request): return await mcp_server.handle_rpc_request(request)
    uvicorn.run(app, host="127.0.0.1", port=8002)