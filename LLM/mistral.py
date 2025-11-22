from dotenv import load_dotenv
from mistralai import Mistral
from mistralai.models import UserMessage
from config import PROMPT_FILE
from utils.logger import get_logger

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


class Mistral_Client:
    def __init__(self, api_key: str, model: str):
        self.client = Mistral(api_key=api_key)
        self.model = model
        self.prompt = load_prompt()

    async def get_response(self):
        log.debug("Sending prompt to Mistral model...")
        response = await self.client.chat.complete_async(
            model=self.model, messages=[UserMessage(content=self.prompt)]
        )
        if response is None:
            log.error("No response from Mistral model")
            return None
        return response
