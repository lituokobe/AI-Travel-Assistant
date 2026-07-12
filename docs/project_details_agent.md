# Project Details - Agent
> This is project that leverages LangChain's DeepAgent framework to create a self-planning multi-agent system to handle complex tasks to serve user's request for travel.
> This document is explaining how the core agent in ./agent works in this project.

## Structure:
The project uses a full set of harness engineering to carefully orchestrate the flow of the system.

The main agent is responsible to
- directly engage wth the user
- identify the user's requests
- create the to-do list (DeepAgent's build in capability)
- answer general/non-specialized questions with its own tools and capabilities.
- initiate sub agents according to the tasks
- delegate the tasks to the sub agents consequently

The sub agents are responsible to
- take the delegated tasks from the main agent
- use their own tools and capabilities to complete the tasks
- report back to the main agent

## Main Agent
The main agent is the brain of the backend agent system, and it dynamically arranges the workflow and the resources.  
It will execute following tasks upon starting:
- Initiate the sandbox from the sandbox server to provide a clean backend for each user engagement.
- Load AGENTs.md as the long-term memory.
- Load MCP tools and middleware for all the child agents.
- Load all the configuration of the sub agents and build them with the tools and middleware.
- Load its own tools including `web_search`, `request_travel_info`, `assign_skill`, `download_sandbox_file` for managing the whole agent system.
- Load its own middleware including 
  - `SkillsSyncMiddleware`
  - `UserSkillsRestoreMiddleware`
  - `build_summarization_middleware`
  - `MemoryUpdateMiddleware`
  - `ModelCallLimitMiddleware`
  - `ToolCallLimitMiddleware`

## Sub Agents
- There are four sub agents that take care different areas of travel tasks for the user:
  - `car_subagent`: Car rental management specialist. Handles searching available car rentals, booking rentals, updating rental dates, and cancelling reservations.
  - `activity_subagent`: Activity recommendation and booking specialist. Handles searching curated activity recommendations, booking activities, updating activity details, and cancelling bookings.
  - `flights_subagent`: Flight booking management specialist. Handles retrieving a passenger's existing tickets, searching available flights, rebooking tickets to new flights, and cancelling tickets.
  - `hotels_subagent`: Hotel booking management specialist. Handles searching available hotels, making reservations, updating check-in/check-out dates, and cancelling bookings.
- The sub agents are configured in the YAML files in `./agent/sub_agents/configs`
- The sub agents' middleware only include `ModelCallLimitMiddleware` and `ToolCallLimitMiddleware` to apply basic limits

## Tools
The agent tools are hosted on the local MCP server at http://localhost:8000, please see the details in `./mcp_server`

## Sandbox
The sandbox is hosted from a cloud sandbox server with opensandbox by Alibaba.

## Data and Memory Management
- The sub agent tools will need to interact with the data base `data/data_base/travel_new.sqlite` to retrieve and update data. This is a simulated database updated each time upload the starting of the agent.
- The short-term memory is stored in Redis.
- The long-term memory is stored in MongoDB.