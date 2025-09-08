import os
import uvicorn
import googlemaps
import re
import json
import ast
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from twilio.rest import Client
# --- LangChain and Gemini Imports ---
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.agents import AgentExecutor, create_structured_chat_agent
from langchain.tools import StructuredTool
from langchain_core.prompts import PromptTemplate
from pydantic import BaseModel, Field

# Load environment variables from the root .env file
load_dotenv()

# ==============================================================================
# 1. SETUP THE REAL-WORLD TOOLS
# ==============================================================================
gmaps = googlemaps.Client(key=os.environ.get("GOOGLE_MAPS_API_KEY"))

def find_alternative_destinations(query: str, location_hint: str) -> str:
    """Finds real, nearby places based on a text query and a text-based location hint."""
    print(f"--- TOOL CALLED: find_alternative_destinations(query='{query}', location_hint='{location_hint}') ---")
    try:
        geocode_result = gmaps.geocode(location_hint)
        if not geocode_result: return f"Error: Could not find coordinates for '{location_hint}'."
        lat, lng = geocode_result[0]['geometry']['location']['lat'], geocode_result[0]['geometry']['location']['lng']
        places_result = gmaps.places_nearby(location=(lat, lng), keyword=query, rank_by='distance')
        if not places_result.get('results'): return "No alternative destinations found nearby."
        top_results = [{"name": p.get('name'), "address": p.get('vicinity'), "rating": p.get('rating', 'N/A')} for p in places_result['results'][:3]]
        return str(top_results)
    except Exception as e: return f"Error using Google Maps APIs: {e}"

def get_new_route_details(origin_hint: str, destination_address: str) -> str:
    """Calculates the new route, distance, and ETA using the Directions API."""
    print(f"--- TOOL CALLED: get_new_route_details(origin_hint='{origin_hint}', destination_address='{destination_address}') ---")
    try:
        directions_result = gmaps.directions(origin_hint, destination_address, mode="driving")
        if not directions_result: return "Error: Could not calculate a route."
        leg = directions_result[0]['legs'][0]
        return f"New route found. Distance: {leg['distance']['text']}. ETA: {leg['duration']['text']}."
    except Exception as e: return f"Error using Directions API: {e}"

# Add this new tool function
def calculate_new_fare(distance_text: str, duration_text: str) -> str:
    """Calculates a simulated new fare based on distance and duration text."""
    print(f"--- TOOL CALLED: calculate_new_fare(distance_text='{distance_text}', duration_text='{duration_text}') ---")
    try:
        distance_km = float(re.findall(r"[\d\.]+", distance_text)[0])
        duration_min = float(re.findall(r"[\d\.]+", duration_text)[0])
        # Formula: Base fare + $2/km + $0.5/min (example rates)
        new_fare = 2.50 + (2 * distance_km) + (0.5 * duration_min)
        return f"The estimated new fare for the updated trip is ${new_fare:.2f}."
    except Exception:
        return "Could not calculate the new fare."

# Add this new tool function
def notify_passenger_via_twilio(message: str) -> str:
    """Sends a final notification to the passenger via Twilio SMS."""
    print(f"--- TOOL CALLED: notify_passenger_via_twilio(message='{message}') ---")
    try:
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        twilio_phone = os.environ.get("TWILIO_PHONE_NUMBER")
        your_phone = os.environ.get("YOUR_PHONE_NUMBER")
        if not all([account_sid, auth_token, twilio_phone, your_phone]):
            return "Twilio credentials are not fully configured."
        client = Client(account_sid, auth_token)
        sms = client.messages.create(body=f"[LOGIA Reroute] {message}", from_=twilio_phone, to=your_phone)
        return "Passenger notification successfully sent via Twilio."
    except Exception as e:
        return f"Error sending Twilio notification: {e}"    

# Define Pydantic models for structured tool inputs
class AlternativeDestinationsInput(BaseModel):
    query: str = Field(description="Search query for the type of place or specific place name")
    location_hint: str = Field(description="Text-based location hint where to search")

class RouteDetailsInput(BaseModel):
    origin_hint: str = Field(description="Starting location as text")
    destination_address: str = Field(description="Destination address as text")

class NotifyPassengerInput(BaseModel):
    message: str = Field(description="Message to send to the passenger")

class FareCalculatorInput(BaseModel):
    distance_text: str = Field(description="The distance of the new route, e.g., '5.2 km'")
    duration_text: str = Field(description="The duration of the new route, e.g., '12 mins'")    

# ==============================================================================
# 2. SETUP THE LANGCHAIN AGENT ("The Brain")
# ==============================================================================
class LangChainReroutingAgent:
    def __init__(self):
        self.llm = ChatGoogleGenerativeAI(
            model="gemini-1.5-flash-latest",
            google_api_key=os.environ.get("GEMINI_API_KEY"),
            temperature=0.0,
        )

    async def _extract_query_and_location(self, scenario: str) -> tuple[str, str]:
        
        instruction = (
            "From the user's request, extract a generic search query for an alternative and a location hint. "
            "If the user mentions a specific business like 'Kritunga' or 'McDonalds', the query should be 'restaurant'. "
            "If they mention 'Starbucks', the query should be 'coffee shop'. "
            "If they mention a generic type like 'pizza place', use that directly. "
            "The goal is to find *alternatives* to what the user mentioned.\n"
            "Return strict JSON with keys 'query' and 'location_hint' only, no prose."
        )
        prompt = f"{instruction}\nScenario: {scenario}"
        ai_message = await self.llm.ainvoke(prompt)
        content = getattr(ai_message, "content", "") or "{}"
        try:
            data = json.loads(content)
        except Exception:
            # Try to recover a JSON object if the model added extra text
            match = re.search(r"\{[\s\S]*\}", content)
            data = json.loads(match.group(0)) if match else {"query": "", "location_hint": ""}
        query = (data.get("query") or "").strip()
        location_hint = (data.get("location_hint") or "").strip()
        return query, location_hint

    @staticmethod
    def _parse_alternatives(result_text: str):
        try:
            return ast.literal_eval(result_text)
        except Exception:
            return []

    @staticmethod
    def _choose_best(alternatives):
        def rating_of(item):
            try:
                return float(item.get("rating", 0) or 0)
            except Exception:
                return 0.0
        return max(alternatives, key=rating_of) if alternatives else None

    @staticmethod
    def _extract_distance_duration(route_text: str) -> tuple[str, str]:
        dist_match = re.search(r"Distance:\s*([^\.]+)", route_text)
        dur_match = re.search(r"ETA:\s*([^\.]+)", route_text)
        distance_text = dist_match.group(1).strip() if dist_match else ""
        duration_text = dur_match.group(1).strip() if dur_match else ""
        return distance_text, duration_text

    # MODIFIED FUNCTION: Simplified to format all given locations
    @staticmethod
    def _format_all_found_locations(locations, max_items: int = 3) -> str:
        """Formats a list of location dictionaries into a readable string."""
        if not locations:
            return "No other locations found nearby."
        
        lines = []
        for item in locations[:max_items]:
            name = item.get("name", "Unknown")
            address = item.get("address", "Unknown address")
            rating = item.get("rating", "N/A")
            lines.append(f"{name} | ⭐ {rating} | {address}")
            
        return "; ".join(lines)

    async def run(self, scenario: str) -> str:
        try:
            reasoning_log = []
            def log(step: str):
                reasoning_log.append(step)
                print(f"[LOGIA REASONING] {step}")

            log("Start reroute flow")
            log(f"Scenario: {scenario}")
            
            # 1) Single LLM call to understand intent
            query, location_hint = await self._extract_query_and_location(scenario)
            log(f"Extracted intent -> query='{query}', location_hint='{location_hint}'")
            if not query or not location_hint:
                return "Could not understand scenario. Please provide the place and approximate location."

            # 2) Find alternatives via tool
            alt_text = find_alternative_destinations(query=query, location_hint=location_hint)
            all_found_locations = self._parse_alternatives(alt_text)
            log(f"find_alternative_destinations -> Found {len(all_found_locations)} locations: {all_found_locations}")

            # ==================================================================
            # ✨ FIX 1: Prevent choosing the original destination ✨
            # Assume the first result is the original/closed one and choose from the rest.
            # ==================================================================
            options_for_reroute = all_found_locations[1:] if len(all_found_locations) > 1 else []
            best = self._choose_best(options_for_reroute)
            log(f"Choosing from options: {options_for_reroute}")
            log(f"Chosen best alternative -> {best}")
            
            if not best:
                notify_passenger_via_twilio(message=f"Sorry, we couldn't find a suitable alternative for '{query}' near '{location_hint}'.")
                return "No suitable alternative destinations found nearby."

            # 3) Get route details
            destination_address = best.get("address", "")
            route_text = get_new_route_details(origin_hint=location_hint, destination_address=destination_address)
            log(f"get_new_route_details -> {route_text}")
            distance_text, duration_text = self._extract_distance_duration(route_text)
            log(f"Parsed route -> distance='{distance_text}', duration='{duration_text}'")

            # 4) Fare estimate
            fare_text = calculate_new_fare(distance_text=distance_text, duration_text=duration_text)
            log(f"calculate_new_fare -> {fare_text}")

            # ==================================================================
            # ✨ FIX 2: Show all alternatives in the final output ✨
            # Call the simplified formatting function on the complete list.
            # ==================================================================
            all_locations_text = self._format_all_found_locations(locations=all_found_locations, max_items=3)

            # 5) Notify passenger
            message = (
                f"Proposed reroute to {best.get('name')} ({destination_address}). "
                f"ETA: {duration_text}. Distance: {distance_text}. {fare_text} "
                f"All found locations nearby: {all_locations_text}"
            )
            notify_result = notify_passenger_via_twilio(message=message)
            log(f"notify_passenger_via_twilio -> {notify_result}")

            # 6) Final answer
            final_summary = (
                f"Reroute complete. Selected: {best.get('name')} at {destination_address}. "
                f"{route_text} {fare_text} All Found Nearby: {all_locations_text}. Notification: {notify_result}"
            )
            full_output = (
                "==== Reasoning Log ====\n" + "\n".join(reasoning_log) + "\n\n" +
                "==== Final Answer ====\n" + final_summary
            )
            return full_output
        except Exception as e:
            error_message = f"🔥🔥🔥 AGENT EXECUTION FAILED 🔥🔥🔥\nError: {e}"
            print(error_message)
            return error_message
# ==============================================================================
# 3. CREATE THE MCP SERVER (The Agent's "Body")
# ==============================================================================
class ReroutingMCP_Server:
    def __init__(self):
        self.agent = LangChainReroutingAgent()
        self.tool_definition = [{"name": "cab/rerouteRequest", "title": "Handle Cab Rerouting Request"}]
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
    print("🚕 LOGIA Cab Rerouting Agent (MCP Server) Starting...")
    mcp_server = ReroutingMCP_Server()
    app = FastAPI(title="LOGIA Rerouting Agent")
    @app.post("/")
    async def rpc_endpoint(request: Request): return await mcp_server.handle_rpc_request(request)
    uvicorn.run(app, host="127.0.0.1", port=8003)