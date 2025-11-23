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
        self.page: Optional[uc.Tab] = None
        self.tweets_to_process: List[uc.Element] = []

    async def create_browser(self, index: int = 0) -> uc.Browser:
        self.browser = await super().create_browser()
        cookie_params = self.load_auth_token_from_txt(index)
        await self.browser.connection.send(uc.cdp.storage.set_cookies(cookie_params))
        return self.browser

    async def find_and_click(self, text: str):
        if isinstance(self.page, uc.Tab):
            element: Optional[uc.Element] = await self.page.find(
                text, best_match=True, timeout=5
            )
            if isinstance(element, uc.Element):
                log.debug(f"Clicking element with text '{text}'.")
                await element.click()
            else:
                log.warning(f"Element with text '{text}' not found.")

    async def goto_target(self, url: str = X_URL) -> uc.Tab:
        if self.browser is None:
            raise RuntimeError("Browser not initialized. Call create_browser() first.")
        log.debug(f"Navigating to {url}")
        self.page = await self.browser.get(url)
        await self.find_and_click("Refuse non-essential cookies")  # cookies
        return self.page

    async def go_back(self):
        if isinstance(self.page, uc.Tab):
            await self.page.back()
            await asyncio.sleep(1)

    async def collect_feed_tweets(self) -> List[uc.Element]:
        if not self.page:
            return []
        try:
            # Get the text containers
            tweet_divs = await self.page.select_all('div[data-testid="tweetText"]')
            valid_tweets = []
            for div in tweet_divs:
                text = div.text_all.strip()
                if self._get_alphanumeric_count(text) >= MIN_X_LENGTH:
                    valid_tweets.append(div)
            return valid_tweets
        except Exception as e:
            log.error(f"Error collecting tweets: {e}")
            return []

    async def click_element_containing_text(self, element: uc.Element):
        try:
            target = element.parent if element.parent else element
            await target.scroll_into_view()
            await asyncio.sleep(0.5)
            await target.click()
        except Exception as e:
            log.error(f"Could not click tweet: {e}")

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
        if (self.page is None) or (self.browser is None):
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

    # --- Interaction Methods (intended for Tweet Detail View) ---
    async def like_current_tweet(self):
        if isinstance(self.page, uc.Tab):
            try:
                like_btn = await self.page.select(
                    'button[data-testid="like"]', timeout=3
                )
                if like_btn:
                    await like_btn.click()
                    log.info("Action: Liked tweet.")
                    return True
            except Exception as e:
                log.warning(f"Failed to like: {e}")
            return False

    async def repost_tweet(self):
        if isinstance(self.page, uc.Tab):
            try:
                retweet_menu_btn = await self.page.select(
                    'button[data-testid="retweet"]', timeout=3
                )
                if retweet_menu_btn:
                    await retweet_menu_btn.click()
                    await asyncio.sleep(0.5)
                    confirm_btn = await self.page.select(
                        'div[data-testid="retweetConfirm"]', timeout=3
                    )
                    if confirm_btn:
                        await confirm_btn.click()
                        log.info("Action: Reposted tweet.")
                        return True
            except Exception as e:
                log.warning(f"Failed to repost: {e}")
            return False

    async def comment_current_tweet(self, text: str):
        if isinstance(self.page, uc.Tab):
            try:
                input_area = await self.page.select(
                    'div[data-testid="tweetTextarea_0"]', timeout=3
                )
                if input_area:
                    await input_area.click()
                    await self.page.send_keys(text)
                    await asyncio.sleep(1)
                    post_btn = await self.page.select(
                        'button[data-testid="tweetButtonInline"]', timeout=3
                    )
                    if post_btn:
                        await post_btn.click()
                        log.info("Action: Replied to tweet.")
                        return True
            except Exception as e:
                log.warning(f"Failed to reply: {e}")

    async def quote_current_tweet(self, text: str):
        if isinstance(self.page, uc.Tab):
            try:
                # 1. Click the Retweet Loop Icon
                retweet_menu_btn = await self.page.select(
                    'button[data-testid="retweet"]', timeout=3
                )
                if retweet_menu_btn:
                    await retweet_menu_btn.click()
                    await asyncio.sleep(0.5)
                    # 2. Click "Quote" from the dropdown
                    quote_btn = await self.page.select(
                        'a[href="/compose/post"]', timeout=3
                    )
                    if quote_btn:
                        await quote_btn.click()
                        await asyncio.sleep(1)

                        # 3. Type text
                        # Focus input area
                        input_area = await self.page.select(
                            'div[data-testid="tweetTextarea_0"]', timeout=3
                        )
                        if input_area:
                            await input_area.click()
                            await self.page.send_keys(text)
                            await asyncio.sleep(1)

                            # 4. Click Post
                            post_btn = await self.page.select(
                                'button[data-testid="tweetButton"]', timeout=3
                            )
                            if post_btn:
                                await post_btn.click()
                                log.info("Action: Quoted tweet.")
                                return True
            except Exception as e:
                log.warning(f"Failed to quote: {e}")
            return False

    # --- Auth token cookies ---
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
