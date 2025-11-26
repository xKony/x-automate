import json
import os
from dotenv import load_dotenv
from mistralai import Mistral
from mistralai.models import UserMessage
from config import PROMPT_FILE, DEFAULT_MODEL
from utils.logger import get_logger
from typing import Optional

load_dotenv()
log = get_logger(__name__)


def load_prompt(prompt_path: str = PROMPT_FILE) -> str:
    log.debug(f"Attempting to load prompt from: {prompt_path}")
    try:
        if not os.path.exists(prompt_path):
            log.error(f"Prompt file not found at path: {prompt_path}")
            raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

        with open(prompt_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        if not content:
            log.warning(f"Prompt file exists but is empty: {prompt_path}")
            return ""

        log.info(f"Successfully loaded prompt ({len(content)} chars)")
        return content

    except Exception as e:
        log.error(f"Error loading prompt file: {e}")
        raise e


class Mistral_Client:
    def __init__(self, model: str = DEFAULT_MODEL):
        # Mask API key in logs for security
        api_key: Optional[str] = os.getenv("MISTRAL_API_KEY")
        if not api_key:
            log.error("Environment variable MISTRAL_API_KEY not set.")
            return
        masked_key = (
            f"{api_key[:4]}...{api_key[-4:]}"
            if api_key and len(api_key) > 8
            else "INVALID"
        )
        log.debug(f"Initializing Mistral Client. Model: {model}, Key: {masked_key}")

        self.client = Mistral(api_key=api_key)
        self.model = model
        try:
            self.base_prompt = load_prompt()
        except Exception as e:
            log.critical(
                "Failed to initialize Mistral Client due to prompt loading error."
            )
            raise e

        log.info("Mistral Client initialized successfully.")

    async def get_response_raw(self, final_prompt: str):
        log.info(f"Sending prompt to Mistral model ({self.model})...")
        try:
            response = await self.client.chat.complete_async(
                model=self.model, messages=[UserMessage(content=final_prompt)]
            )
            if response is None:
                log.error("Received None response from Mistral API.")
            else:
                log.debug("Received raw response from Mistral API.")
            return response
        except Exception as e:
            log.error(f"Exception during Mistral API call: {e}")
            return None

    def parse_response(self, response):
        if response is None:
            log.warning("Cannot parse None response.")
            return None

        log.debug(f"Parsing response of type: {type(response)}")
        try:
            content = None

            # 1. Try standard object attribute access (Choices)
            if hasattr(response, "choices"):
                choices = getattr(response, "choices")
                if choices:
                    first = choices[0]
                    if hasattr(first, "message") and hasattr(first.message, "content"):
                        content = first.message.content
                    elif isinstance(first, dict):
                        content = first.get("message", {}).get("content")

            # 2. Fallback to output_text or text
            if not content:
                if hasattr(response, "output_text"):
                    content = getattr(response, "output_text")
                elif hasattr(response, "text"):
                    content = getattr(response, "text")

            # 3. Last resort: String conversion
            if content is None:
                content = str(response)

            return content

        except Exception as e:
            log.error(f"Failed parsing Mistral response: {e}", exc_info=True)
            return str(response)

    def _extract_reply_from_json(self, raw_text: str) -> Optional[str]:
        try:
            # Clean up markdown code blocks if present (common LLM behavior)
            clean_text = raw_text.replace("```json", "").replace("```", "").strip()

            data = json.loads(clean_text)

            # The prompt returns a list of objects
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("reply")
            elif isinstance(data, dict):
                return data.get("reply")

            log.warning(f"JSON parsed but structure unexpected: {data}")
            return clean_text  # Fallback to full text if structure is wrong

        except json.JSONDecodeError:
            log.warning("LLM response was not valid JSON. Returning raw text.")
            return raw_text
        except Exception as e:
            log.error(f"Error parsing JSON reply: {e}")
            return raw_text

    async def get_response(self, tweet_text: str):
        log.info("Starting response generation sequence...")

        tweet_input: str = json.dumps({"id": 1, "text": tweet_text}, ensure_ascii=False)

        # 2. Inject into the prompt template
        if "[TWEET_IN_JSON]" in self.base_prompt:
            final_prompt = self.base_prompt.replace("[TWEET_IN_JSON]", tweet_input)
        else:
            log.warning(
                "Placeholder [TWEET_IN_JSON] not found in prompt file. Appending text."
            )
            final_prompt = f"{self.base_prompt}\n\nTweet Input:\n{tweet_input}"

        # 3. Call API
        raw = await self.get_response_raw(final_prompt)

        if raw:
            # 4. Extract raw content string
            content_str = self.parse_response(raw)
            if not content_str:
                return None

            # 5. Parse the specific JSON format to get the clean reply
            final_reply = self._extract_reply_from_json(content_str)

            log.info(f"Generated Reply: {final_reply}")
            return final_reply
        else:
            log.error("Response generation failed (No raw response).")
            return None
