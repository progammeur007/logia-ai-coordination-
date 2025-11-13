# 🚚 LOGIA: Logistics Intelligence Agent

> A Multi-Agent AI Coordination System for autonomously resolving last-mile delivery disruptions using the Model Context Protocol (MCP).

LOGIA (Logistics Intelligence Agent) is a framework designed to bring autonomous, real-time problem-solving to the chaotic world of last-mile delivery.

Instead of a single, monolithic AI trying to handle everything, LOGIA deploys a **team of specialized AI agents**. Each agent is an expert in one specific domain (e.g., safety, rerouting, delays). They communicate and coordinate through a central hub, allowing them to work together to manage complex, real-world disruptions like traffic, restaurant delays, and passenger emergencies.

## 🤖 Core Architecture

The system is built on a simple, powerful, and scalable model:

### 1. MCP Server (`mcp/server.py`)
This is the central "air traffic controller" for all agents. It's not an agent itself, but a lightweight coordination hub. It facilitates communication, allowing agents to call each other's tools and work together without being directly coupled.

### 2. Specialized Agents (`agents/`)
These are individual Python clients that connect to the MCP server. Each one is "siloed" and only knows how to do its specific job, making it highly effective and easy to maintain.

---

## 🚀 Meet the Agents

LOGIA's strength comes from its team of specialized agents. Here are the agents currently deployed:

### 🚨 Safety Agent
* **Purpose:** Provides real-time, in-transit safety monitoring.
* **Function:** This agent is designed to listen to an audio stream (e.g., from a driver's app) for specific distress-related keywords ("help," "save me," "danger," etc.). When it detects a trigger phrase, it immediately flags the event and escalates it, providing a critical layer of safety for passengers and drivers.

### 🗺️ Rerouting Agent
* **Purpose:** Manages on-the-fly trip changes requested by passengers.
* **Function:** This agent handles scenarios where a passenger is en route but needs to change their destination (e.g., "The restaurant I was going to is closed, find me another one nearby!").
* **Key Logic:**
    1.  It intelligently extracts the *category* of the new destination (e.g., "restaurant"), not just the original name ("Kritunga").
    2.  It uses the Google Maps API to find the **best-rated alternative** (excluding the original destination).
    3.  It calculates the new route, ETA, and fare.
    4.  It sends a detailed notification to the passenger with all the new details.

### 🍔 Food Delay & Cancellation Agent
* **Purpose:** Manages critical, restaurant-side food order delays.
* **Function:** This agent handles the complex domino effect of a restaurant being overloaded. Its goal is to minimize disruption for the customer and maximize efficiency for the driver.
* **Key Logic:**
    1.  **Orchestrator Model:** Instead of many slow, back-and-forth LLM calls, this agent uses a single, powerful "Orchestrator" tool.
    2.  **Multi-Action Response:** In *one unified step*, the agent gathers all data, finds a new, efficient task for the driver (to prevent them from waiting), and simultaneously sends a detailed, helpful notification to the customer offering alternatives and compensation.

---

## ⚙️ Setup and Installation

1.  **Clone the repository:**
    ```bash
    git clone https://your-repo-url/logia-ai-coordination.git
    cd logia-ai-coordination
    ```

2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Set up your environment:**
    Create a `.env` file in the root directory and add your necessary API keys.
    ```ini
    # .env
    GOOGLE_MAPS_API_KEY=AI...
    GEMINI_API_KEY=AI...
    
    # Twilio (for notifications)
    TWILIO_ACCOUNT_SID=AC...
    TWILIO_AUTH_TOKEN=...
    TWILIO_PHONE_NUMBER=+1...
    YOUR_PHONE_NUMBER=+1... 
    ```

---

## 🚀 How to Run

LOGIA's agents run as separate processes. You must first start the central server and then launch each agent you want to activate in its own terminal.

1.  **Start the MCP Server:**
    Open a terminal and run the server. This is the central hub and must be running.
    ```bash
    # In Terminal 1
    python mcp/server.py
    ```

2.  **Run the Agents:**
    Open a *new terminal* for each agent you want to run. They will automatically connect to the server.

    ```bash
    # In Terminal 2
    python agents/safety_agent.py
    ```

    ```bash
    # In Terminal 3
    python agents/rerouting_agent.py
    ```

    ```bash
    # In Terminal 4
    python agents/food_delay_agent.py
    ```

The system is now live. The agents are listening on the MCP server for their respective tool calls.

---

## 📊 Project Status

-   [x] **MCP Server:** Core coordination hub is operational.
-   [x] **Safety Agent:** Deployed and monitoring for distress signals.
-   [x] **Rerouting Agent:** Deployed and handling passenger route changes.
-   [x] **Food Delay Agent:** Deployed and managing restaurant-side delays.
