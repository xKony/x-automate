import random
import nodriver as uc
import asyncio
import json
from utils.nodriver_utils import BaseBrowser
from utils.logger import get_logger
from typing import Optional, List, Dict, Any
from config import HEADLESS_BROWSER, X_URL, MIN_X_LENGTH, COOKIES_FILE, AUTH_TOKENS_FILE

log = get_logger(__name__)


class XBrowser(BaseBrowser):
    def __init__(self, headless: bool = HEADLESS_BROWSER):
        super().__init__(headless=headless)
        self.target: Optional[uc.Tab] = None
        self.tweets_to_process: List[uc.Element] = []

    async def create_browser(self, index: int = 0) -> uc.Browser:
        self.browser = await super().create_browser()
        cookie_params = self.load_auth_token_from_txt(index)
        await self.browser.connection.send(uc.cdp.storage.set_cookies(cookie_params))
        return self.browser

    async def goto_target(self, url: str = X_URL):
        if self.browser is None:
            raise RuntimeError("Browser not initialized. Call create_browser() first.")
        self.target = await self.browser.get(url)
        return self.target

    async def find_and_click(self, text: str):
        if isinstance(self.target, uc.Tab):
            element = await self.target.find(text, best_match=True)
            if element:
                await element.click()

    async def collect_valid_tweets(self) -> List[Dict[str, Any]]:
        if (self.target is None) or (self.browser is None):
            return []

        try:
            tweet_divs: List[uc.Element] = await self.page.select_all(
                'div[data-testid="tweetText"]'
            )
            collected_data = []

            if not tweet_divs:
                log.info("No tweets found.")
                return []

            log.info(f"Found {len(tweet_divs)} raw tweets. Filtering...")

            for index, div in enumerate(tweet_divs):
                text = div.text_all.strip()

                # Filter: Check length
                if self._get_alphanumeric_count(text) < MIN_X_LENGTH:
                    continue

                collected_data.append(
                    {
                        "id": index,
                        "tweet_content": text,
                        "element": div,
                        "parent": div.parent if div.parent else div,
                    }
                )

            return collected_data

        except Exception as e:
            log.error(f"Error collecting tweets: {e}")
            return []

    async def process_single_tweet(self, div: uc.Element, index: int):
        text: str = div.text_all.strip()
        current_tweet = div.parent if div.parent else div
        log.debug(f"\nTweet {index}: {text} \n")
        if self._get_alphanumeric_count(text) < MIN_X_LENGTH:
            print(f"Tweet {index} skipped (too short)")
            return
        try:
            await current_tweet.scroll_into_view()
            await asyncio.sleep(random.uniform(0.5, 2.5))
            await current_tweet.mouse_click(button="left")
            log.debug(f"Clicked tweet {index}")
        except Exception as e:
            log.error(f"Failed to interact with tweet {index}: {e}")

    async def load_tweets(self):
        if (self.target is None) or (self.browser is None):
            return
        try:
            tweet_divs: List[uc.Element] = await self.page.select_all(
                'div[data-testid="tweetText"]'
            )
            if tweet_divs:
                log.info(f"Found {len(tweet_divs)} tweets. Starting processing...")

                for i, div in enumerate(tweet_divs, start=1):
                    await self.process_single_tweet(div, i)
            else:
                log.info("No tweets found.")
        except Exception as e:
            log.error(f"Error loading tweets: {e}")

    async def like_tweet(self):
        if isinstance(self.target, uc.Tab):
            like_button = await self.target.select(
                'button[data-testid="like"]', timeout=5
            )
            if like_button:
                await like_button.click()

    def load_auth_token_from_txt(
        self, line_index: int = 0, filepath: str = AUTH_TOKENS_FILE
    ) -> List[uc.cdp.network.CookieParam]:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                tokens = [line.strip() for line in f if line.strip()]
            if not tokens:
                raise ValueError(f"File {filepath} is empty.")
            if line_index >= len(tokens):
                raise ValueError(
                    f"Index {line_index} out of bounds. Only {len(tokens)} tokens found."
                )
            target_token = tokens[line_index]
            log.debug(
                f"Loaded auth token {target_token} from line {line_index} in {filepath}."
            )
            return [
                self._create_auth_cookie(target_token, ".x.com"),
                self._create_auth_cookie(
                    target_token, ".twitter.com"
                ),  # we do it for both domains to be safe
            ]

        except FileNotFoundError:
            log.error(f"Auth token file not found: {filepath}")
            raise

    def _get_alphanumeric_count(self, text: str) -> int:
        return sum(map(str.isalnum, text))

    def _create_auth_cookie(
        self, token: str, domain: str
    ) -> uc.cdp.network.CookieParam:
        return uc.cdp.network.CookieParam(
            name="auth_token",
            value=token,
            domain=domain,
            path="/",
            secure=True,
            http_only=True,
            # same_site=uc.cdp.network.CookieSameSite.LAX,  # Good practice for nav
            expires=None,
        )
