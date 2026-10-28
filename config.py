"""Configuration for the Self-Healing AI Automation System."""

import os
from dotenv import load_dotenv

load_dotenv()

# Server
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# AI Provider - supports "gemini" or "rule_based" (fallback)
AI_PROVIDER = os.getenv("AI_PROVIDER", "rule_based")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Healing Settings
AUTO_APPROVE_CONFIDENCE_THRESHOLD = float(os.getenv("AUTO_APPROVE_THRESHOLD", "0.90"))
MAX_RETRY_ATTEMPTS = int(os.getenv("MAX_RETRY_ATTEMPTS", "3"))
RETRY_DELAY_SECONDS = float(os.getenv("RETRY_DELAY_SECONDS", "1.0"))

# Monitoring
MONITOR_POLL_INTERVAL = float(os.getenv("MONITOR_POLL_INTERVAL", "0.5"))
