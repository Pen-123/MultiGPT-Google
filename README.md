MultiGPT Google Chat Webhook

A high-performance, stateless AI bot migrated from Discord to Google Chat, optimized for deployment as a Render Web Service. This bot features multiple personality modes, advanced image/video/audio generation, and persistent memory per user.

🚀 Deployment on Render

1. Repository Setup

Ensure your GitHub repository contains the following core files:

main.py: The ported Google Chat logic.

requirements.txt: Project dependencies.

LICENSE: Your project license.

2. Render Web Service Configuration

When creating your Web Service on Render, use these settings:

Runtime: Python 3

Build Command: pip install -r requirements.txt

Start Command: python main.py

3. Environment Variables

Configure the following variables in the Render Dashboard:

Variable

Description

Requirement

GROQ_API_KEY

Primary API key for LLM processing

Required

GROQ_API_KEY2

Secondary key for automatic rotation

Optional

HF_TOKEN

Hugging Face token for Smart Image generation

Optional

HF_IMAGES

ImgBB API Key used for hosting generated images

Optional

SILICONFLOW_API_KEY

Key for Wan-AI video generation

Optional

POLLINATIONS_API_KEY

Key for music/audio generation

Optional

🔗 Google Cloud & Chat Configuration

To connect the bot to Google Chat, follow these steps in the Google Cloud Console:

1. Identify Your Project Details

Project Name: The display name of your project.

Project ID: A unique string (e.g., multigpt-bot-456789). Use this for identification.

Project Number: A unique number (e.g., 123456789012). Required for some API permissions.

2. Enable APIs

Go to APIs & Services > Library.

Search for and enable the Google Chat API.

3. Configure Google Chat API

Go to APIs & Services > Enabled APIs & Services > Google Chat API > Configuration:

App name: MultiGPT

Avatar URL: (Optional) Link to a bot icon.

Description: Advanced AI assistant with multi-model support.

Functionality: Enable Receive 1:1 messages and Join spaces.

Connection Settings: Select HTTP Endpoint.

Endpoint URL: Paste your Render URL here (e.g., https://your-app.onrender.com).

🛠 Features

🎭 Personality Modes

/chill: Default relaxed mission operative.

/unhinged: High-intensity, unfiltered personality.

/coder: Expert programming assistant.

/childish: Immature, meme-heavy persona.

🎨 Creative Tools

/image <prompt>: Generates images via FLUX (Smart) or Pollinations (Fast).

/video <prompt>: Generates 720p video via SiliconFlow (takes 3-15 mins). Use /vp to check status.

/music <prompt>: Generates audio tracks via Pollinations. Use /mp to check status.

🧠 Memory & System

Context Persistence: Use /sm to enable memory and /sc to start a saved chat slot.

LLM Switching: Toggle between models using /change_llm.

Health Monitoring: Includes a /healthz endpoint for Render uptime monitoring.
