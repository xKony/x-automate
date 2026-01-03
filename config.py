# ==============================================================================
# CONFIGURATION SETTINGS
# ==============================================================================

import os

# --- Browser & Driver Settings ---
HEADLESS_BROWSER = False
X_URL = "https://x.com/"
LOG_LEVEL = "DEBUG"
SAVE_LOGS = False

# --- Interaction Probabilities ---
# Main Feed Actions
PROB_LIKE = 0.40      # 40% chance to like a tweet
PROB_REPOST = 0.10    # 10% chance to repost
PROB_REPLY = 0.15     # 15% chance to reply
PROB_QUOTE = 0.05     # 5% chance to quote
PROB_PAGE_REFRESH = 0.15 # 15% chance to refresh page

# Comment/Thread Interactions (New)
PROB_LIKE_COMMENT = 0.05       # 5% chance to like a specific comment/reply
PROB_FOLLOW = 0.90           # 2% chance to follow a user via hover card
PROB_WHO_TO_FOLLOW = 0.90      # 5% chance to follow from "Who to follow" sidebar
MAX_INTERACTIONS_PER_THREAD = 3 # Hard cap on actions (likes/follows) per thread

# --- Simulation Parameters ---
MIN_X_LENGTH = 20     # Min char length to process
MAX_ACTIONS = 20      # Default max activities per account

# --- VPN Settings ---
DEFAULT_VPN_LOCATION = "United States"
VPN_FALLBACK_LIST = ["Germany", "United Kingdom", "Canada"]

# --- File Paths ---
PROMPT_FILE = "LLM/prompts/default_prompt.txt"
COOKIES_FILE = "cookies/cookies.json"
AUTH_TOKENS_FILE = "cookies/auth_tokens.txt"

# --- LLM Settings ---
DEFAULT_MODEL = "mistral-small-latest"
