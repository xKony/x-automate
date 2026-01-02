# x_handling
PROB_LIKE = 0.40  # 40% chance to like
PROB_REPOST = 0.10  # 10% chance to repost
PROB_REPLY = 0.15  # 15% chance to reply
PROB_QUOTE = 0.05  # 5% chance to quote
PROB_PAGE_REFRESH = 0.15  # 15% chance to refresh the page to get new tweets

HEADLESS_BROWSER = True
X_URL = "https://x.com/"
SAVE_LOGS = False
PROMPT_FILE = "LLM/prompts/default_prompt.txt"
COOKIES_FILE = "cookies/cookies.json"
AUTH_TOKENS_FILE = "cookies/auth_tokens.txt"  # keep it very secret
LOG_LEVEL = "DEBUG"
MIN_X_LENGTH = 20  # min length in characters for X post to be processed (its hard to reply to a 10 character post)
DEFAULT_MODEL = "mistral-small-latest"
MAX_ACTIONS = 20  # default max activities per account
