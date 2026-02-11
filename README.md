# NL2Mongo-Agent-LangGraph-create_ReAct_agent-
A production-ready LLM-powered MongoDB query agent built with LangGraph that converts natural language into executable MongoDB queries with conversational memory support.

This project is an AI agent that translates natural language queries into executable MongoDB queries and runs them against your database, enabling conversational interaction with MongoDB via an agent built on LangGraph’s ReAct agent.


**🚀 Features**

**🧠 Natural Language Understanding** — Users express queries in plain English (or other languages), and the agent converts them into MongoDB commands.

**💬 Conversational Interaction** — Ask questions like “Find all users with age > 30” and receive real results from your MongoDB.

**🔧 ReAct Agent Pattern** — Built using LangGraph’s create_react_agent (ReAct = Reason + Act). The agent reasons about user input and decides when/how to call tools.

**📦 Tooling Layer** — Wraps MongoDB operations behind helper functions for safe query execution.

**📇 Dynamic Query Generation** — Generates filter and projection objects that match user intent.


**🧩 Architecture Overview**

Input
A user sends a free-form query (e.g., “List all products under ₹5000”).

Agent Reasoning
The LLM interprets intent, maps it to query components, and constructs a valid MongoDB filter/projection.

Tool Invocation
A helper function executes the generated query against the connected MongoDB instance.

Output
Results are returned conversationally.



**🧠 How It Works**

This system uses a ReAct Agent from LangGraph, which runs in a loop:

Reason → Decide what action to take.

Act → Execute a tool (MongoDB query).

Observe → Inspect results.

Repeat until a final answer is produced
