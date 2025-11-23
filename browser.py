import random
import nodriver as uc
import asyncio
from utils.nodriver_utils import BaseBrowser
from utils.logger import get_logger
from typing import Optional, List
from config import HEADLESS_BROWSER, X_URL, MIN_X_LENGTH

log = get_logger(__name__)


class XBrowser(BaseBrowser):
    def __init__(self, headless: bool = HEADLESS_BROWSER):
        super().__init__(headless=headless)
        self.target: Optional[uc.Tab] = None

    async def create_browser(self):
        self.browser = await super().create_browser()
        self.target = await self.browser.get(X_URL)
        return self.browser

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
        if isinstance(self.page, uc.Tab):
            like_button = await self.page.select(
                'button[data-testid="like"]', timeout=5
            )
            if like_button:
                await like_button.click()

    def _get_alphanumeric_count(self, text: str) -> int:
        return sum(map(str.isalnum, text))
