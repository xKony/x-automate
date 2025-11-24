from dotenv import load_dotenv
from mistralai import Mistral
from mistralai.models import UserMessage
from config import PROMPT_FILE
from utils.logger import get_logger
import json

load_dotenv()  # to access env vars
log = get_logger(__name__)


# loading prompt from file
def load_prompt(prompt: str = PROMPT_FILE) -> str:
    log.debug("Loading prompt from file...")
    with open(prompt, "r", encoding="utf-8") as f:
        if f is None:
            log.error("Prompt file not found")
            raise Exception("Prompt file not found")
        return f.read().strip()
    return ""


class Mistral_Client:
    def __init__(self, api_key: str, model: str):
        self.client = Mistral(api_key=api_key)
        self.model = model
        self.prompt = load_prompt()

    async def get_response_raw(self):
        log.debug("Sending prompt to Mistral model...")
        response = await self.client.chat.complete_async(
            model=self.model, messages=[UserMessage(content=self.prompt)]
        )
        if response is None:
            log.error("No response from Mistral model")
        return response

    def parse_response(self, response):
        if response is None:
            return None
        try:
            content = None
            if hasattr(response, "choices"):
                choices = getattr(response, "choices")
                if choices:
                    first = choices[0]
                    # object-like
                    if hasattr(first, "message") and hasattr(first.message, "content"):
                        content = first.message.content
                    # dict-like
                    elif isinstance(first, dict):
                        content = first.get("message", {}).get("content")

            if not content:
                content = getattr(response, "output_text", None) or getattr(
                    response, "text", None
                )

            if content is None:
                content = str(response)

            if isinstance(content, list):
                content = "\n".join(map(str, content))
            if isinstance(content, dict):
                content = json.dumps(content)

            return content
        except Exception as e:
            log.error(f"Failed parsing Mistral response: {e}")
            return str(response)

    async def get_response(self):
        raw = await self.get_response_raw()
        return self.parse_response(raw)
