import os
import uvicorn
import tempfile
import json
import base64
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv
from twilio.rest import Client

# --- Google Gemini & VADER Imports ---
import google.generativeai as genai
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

# Load environment variables from the root .env file
load_dotenv()

# ==============================================================================
# 1. SETUP THE SPECIALIZED TOOLS
# ==============================================================================

# Initialize the VADER sentiment analyzer once
vader_analyzer = SentimentIntensityAnalyzer()

def analyze_sentiment_with_vader(text: str) -> dict:
    """Uses the offline VADER library to analyze the sentiment of a text."""
    print(f"--- TOOL CALLED: analyze_sentiment_with_vader ---")
    try:
        scores = vader_analyzer.polarity_scores(text)
        return {"compound_score": scores['compound']}
    except Exception as e:
        print(f"🔥 VADER Sentiment Error: {e}")
        return {"compound_score": 0.0}

def notify_officials(summary: str) -> str:
    """Notifies officials by sending a real Twilio SMS."""
    print(f"--- ACTION: Notifying Officials. Details: {summary} ---")
    message = f"CRITICAL SAFETY ALERT from LOGIA! High-priority threat detected. Details: {summary}"
    try:
        # --- THIS IS THE REAL TWILIO LOGIC ---
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        twilio_phone = os.environ.get("TWILIO_PHONE_NUMBER")
        your_phone = os.environ.get("YOUR_PHONE_NUMBER")
        if not all([account_sid, auth_token, twilio_phone, your_phone]):
            return "Twilio credentials are not fully configured."
        
        client = Client(account_sid, auth_token)
        sms = client.messages.create(body=message, from_=twilio_phone, to=your_phone)
        print(f"✅ Successfully sent SMS to officials! SID: {sms.sid}")
        return "Officials have been notified via Twilio."
    except Exception as e:
        print(f"🔥 FAILED to send SMS to officials: {e}")
        return f"Error notifying officials: {e}"

def contact_user(summary: str) -> str:
    """Checks in with the user by sending a real Twilio SMS."""
    print(f"--- ACTION: Contacting User. Details: {summary} ---")
    message = f"LOGIA Check-in: We detected a concerning situation and have logged it for review. Are you okay? Please respond. Record: {summary}"
    try:
        # --- THIS IS THE REAL TWILIO LOGIC ---
        account_sid = os.environ.get("TWILIO_ACCOUNT_SID")
        auth_token = os.environ.get("TWILIO_AUTH_TOKEN")
        twilio_phone = os.environ.get("TWILIO_PHONE_NUMBER")
        your_phone = os.environ.get("YOUR_PHONE_NUMBER")
        if not all([account_sid, auth_token, twilio_phone, your_phone]):
            return "Twilio credentials are not fully configured."

        client = Client(account_sid, auth_token)
        sms = client.messages.create(body=message, from_=twilio_phone, to=your_phone)
        print(f"✅ Successfully sent SMS to user! SID: {sms.sid}")
        return "A check-in message has been sent to the user."
    except Exception as e:
        print(f"🔥 FAILED to send SMS to user: {e}")
        return f"Error contacting user: {e}"

# ==============================================================================
# 2. CREATE THE MAIN "ANALYST" AGENT
# ==============================================================================
class GeminiSafetyAgent:
    def __init__(self):
        try:
            genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
            self.model = genai.GenerativeModel('gemini-1.5-flash-latest')
            print("✅ Gemini multimodal model initialized successfully.")
        except Exception as e:
            self.model = None
            print(f"🔥🔥🔥 FAILED TO INITIALIZE GEMINI LLM 🔥🔥🔥\nError: {e}")

    async def analyze_audio(self, audio_bytes: bytes) -> dict:
        if not self.model: return {"error": "Gemini model not initialized."}
        
        tmp_path = None
        try:
            # --- STAGE 1: TRANSCRIPTION ---
            with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp_file:
                tmp_path = tmp_file.name
                tmp_file.write(audio_bytes)
            
            print(f"--- Stage 1: Transcribing Audio... ---")
            audio_file = genai.upload_file(path=tmp_path)
            transcription_response = await self.model.generate_content_async(["Transcribe this audio file.", audio_file])
            recognized_text = transcription_response.text.strip()
            print(f"   - Recognized Text: '{recognized_text}'")

            if not recognized_text:
                return {"threat_analysis": {"threat_level": "SAFE", "justification": "No speech detected."}}

            # --- STAGE 2: SENTIMENT ANALYSIS (with VADER) ---
            print(f"--- Stage 2: Analyzing Sentiment with VADER... ---")
            sentiment_result = analyze_sentiment_with_vader(recognized_text)
            print(f"   - Sentiment Result: {sentiment_result}")
            
            # --- STAGE 3: FINAL JUDGMENT ---
            print(f"--- Stage 3: Making Final Judgment... ---")
            
            judgment_prompt = f"""You are a safety expert. You must make a final threat assessment based on two pieces of evidence: a text transcript and its sentiment score.

            **Evidence:**
            1.  **Transcript:** "{recognized_text}"
            2.  **Sentiment Score:** {sentiment_result['compound_score']} (This is a compound score from -1.0 (most negative) to 1.0 (most positive).)

            **Your Mandatory Rules:**
            - A 'HIGH' threat requires BOTH high-risk words (help, danger, stop) AND a strongly negative sentiment score (e.g., less than -0.5).
            - A 'MEDIUM' threat occurs if high-risk words are present but the sentiment score is neutral or positive (a conflict).
            - A 'SAFE' threat has no high-risk words and a neutral or positive sentiment score.

            You MUST respond with a JSON object with fields: "threat_level" (one of ["SAFE", "MEDIUM", "HIGH"]), "threat_score" (0.0-10.0), and "justification" (a one-sentence explanation for your decision).
            """
            
            judgment_response = await self.model.generate_content_async(judgment_prompt)
            threat_analysis = json.loads(judgment_response.text.strip().replace("```json", "").replace("```", ""))
            threat_analysis["recognized_text"] = recognized_text # Add transcript for display

            # --- STAGE 4: ACTION ---
            print(f"--- Stage 4: Taking Action... ---")
            action_result = {}
            if threat_analysis.get("threat_level") == "HIGH":
                action = notify_officials(threat_analysis.get("justification"))
                action_result = {"action_taken": action, "chain_of_thought": "Threat was HIGH, notified officials."}
            elif threat_analysis.get("threat_level") == "MEDIUM":
                action = contact_user(threat_analysis.get("justification"))
                action_result = {"action_taken": action, "chain_of_thought": "Threat was MEDIUM, contacted user for check-in."}
            else:
                action_result = {"chain_of_thought": "Threat was SAFE, no action required."}
            
            return {"threat_analysis": threat_analysis, "responder_actions": action_result}

        except Exception as e:
            return {"error": f"An error occurred during analysis: {e}"}
        finally:
            if tmp_path and os.path.exists(tmp_path): os.unlink(tmp_path)

# ==============================================================================
# 3. CREATE THE MCP SERVER (The Agent's "Body")
# ==============================================================================
class SafetyMCP_Server:
    def __init__(self):
        self.agent = GeminiSafetyAgent()
        self.tool_definition = [{"name": "safety/analyzeAudio", "title": "Analyze Audio for Safety Threats"}]
    def mcp_initialize(self, params): return {"capabilities": {"tools": {}}}
    def mcp_tools_list(self, params): return {"tools": self.tool_definition}
    async def mcp_tools_call(self, params):
        audio_base64 = params.get("arguments", {}).get("audio_data")
        if not audio_base64: return {"error": {"message": "audio_data is required."}}
        audio_bytes = base64.b64decode(audio_base64)
        result = await self.agent.analyze_audio(audio_bytes)
        return {"content": [{"type": "dict", "data": result}]}
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
    print("🛡️ LOGIA Advanced Safety Agent (MCP Server) Starting...")
    mcp_server = SafetyMCP_Server()
    app = FastAPI(title="LOGIA Safety Agent")
    @app.post("/")
    async def rpc_endpoint(request: Request): return await mcp_server.handle_rpc_request(request)
    uvicorn.run(app, host="127.0.0.1", port=8001)