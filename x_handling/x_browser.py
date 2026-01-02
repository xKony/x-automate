import random
import nodriver as uc
import asyncio
import json
import os
import re
from datetime import datetime
from utils.base_browser import BaseBrowser
from utils.logger import get_logger
from typing import Optional, List, Dict, Union
from config import HEADLESS_BROWSER, X_URL, MIN_X_LENGTH, COOKIES_FILE, AUTH_TOKENS_FILE

log = get_logger(__name__)


class XBrowser(BaseBrowser):
    def __init__(self, headless: bool = HEADLESS_BROWSER) -> None:
        super().__init__(headless=headless)
        self.page: Optional[uc.Tab] = None
        self.tweets_to_process: List[uc.Element] = []
        self._last_auth_token: Optional[str] = None
        self._last_handle: Optional[str] = None

    async def create_browser(self, index: int = 0) -> uc.Browser:
        self.browser = await super().create_browser()
        cookie_params = self.load_auth_token_from_txt(index)
        await self.browser.connection.send(uc.cdp.storage.set_cookies(cookie_params))
        return self.browser

    # --- Navigating ---

    async def find_and_click(self, text: str) -> None:
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
        # Try to capture the current account handle and persist metadata
        try:
            handle = await self.get_account_handle()
            if handle:
                # store in instance for later metric updates
                self._last_handle = handle
                try:
                    self.save_account_metadata(handle)
                except Exception as e:
                    log.warning(f"Failed saving account metadata: {e}")
        except Exception:
            # non-fatal
            pass
        return self.page

    async def go_back(self) -> None:
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

    async def click_element_containing_text(self, element: uc.Element) -> None:
        try:
            target = element.parent if element.parent else element
            await target.scroll_into_view()
            await asyncio.sleep(0.5)
            await target.click()
        except Exception as e:
            log.error(f"Could not click tweet: {e}")

    async def process_single_tweet(self, div: uc.Element, index: int) -> None:
        text: str = div.text_all.strip()
        current_tweet = div.parent if div.parent else div
        log.debug(f"\nTweet {index}: {text} \n")
        if self._get_alphanumeric_count(text) < MIN_X_LENGTH:
            log.info(f"Tweet {index} skipped (too short)")
            return
        try:
            await current_tweet.scroll_into_view()
            await asyncio.sleep(random.uniform(0.5, 2.5))
            await current_tweet.mouse_click(button="left")
            log.debug(f"Clicked tweet {index}")
        except Exception as e:
            log.error(f"Failed to interact with tweet {index}: {e}")

    async def load_tweets(self) -> None:
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
    async def like_current_tweet(self) -> bool:
        if isinstance(self.page, uc.Tab):
            try:
                like_btn = await self.page.select(
                    'button[data-testid="like"]', timeout=3
                )
                if like_btn:
                    await like_btn.click()
                    log.info("Action: Liked tweet.")
                    try:
                        self.increment_metric("likes")
                    except Exception as e:
                         log.warning(f"Failed to increment like metric: {e}")
                    return True
            except Exception as e:
                log.warning(f"Failed to like: {e}")
            return False
        return False

    async def repost_tweet(self) -> bool:
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
                        try:
                            self.increment_metric("reposts")
                        except Exception as e:
                             log.warning(f"Failed to increment repost metric: {e}")
                        return True
            except Exception as e:
                log.warning(f"Failed to repost: {e}")
            return False
        return False

    async def comment_current_tweet(self, text: str) -> bool:
        if isinstance(self.page, uc.Tab):
            try:
                input_area: uc.Element = await self.page.select(
                    'div[data-testid="tweetTextarea_0"]', timeout=3
                )
                if input_area:
                    await input_area.scroll_into_view()
                    await input_area.click()
                    await input_area.send_keys(text)
                    await asyncio.sleep(1)
                    post_btn: uc.Element = await self.page.select(
                        'button[data-testid="tweetButtonInline"]', timeout=3
                    )
                    if post_btn:
                        await post_btn.click()
                        log.info("Action: Replied to tweet.")
                        try:
                            self.increment_metric("replies")
                        except Exception as e:
                             log.warning(f"Failed to increment reply metric: {e}")
                        return True
            except Exception as e:
                log.warning(f"Failed to reply: {e}")
        return False

    async def quote_current_tweet(self, text: str) -> bool:
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
                        input_area: uc.Element = await self.page.select(
                            'div[data-testid="tweetTextarea_0"]', timeout=3
                        )
                        if input_area:
                            await input_area.click()
                            await input_area.send_keys(text)
                            await asyncio.sleep(1)

                            # 4. Click Post
                            post_btn = await self.page.select(
                                'button[data-testid="tweetButton"]', timeout=3
                            )
                            if post_btn:
                                await post_btn.click()
                                log.info("Action: Quoted tweet.")
                                try:
                                    self.increment_metric("quotes")
                                except Exception as e:
                                     log.warning(f"Failed to increment quote metric: {e}")
                                return True
            except Exception as e:
                log.warning(f"Failed to quote: {e}")
            return False
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
            # store last used token for later persistence
            self._last_auth_token = target_token
            masked_token = (
                f"{target_token[:4]}...{target_token[-4:]}"
                if target_token and len(target_token) > 8
                else "INVALID"
            )
            log.debug(
                f"Loaded auth token {masked_token} from line {line_index} in {filepath}."
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
        except Exception as e:
             log.error(f"Error loading auth token: {e}")
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

    async def get_account_handle(self) -> Optional[str]:
        if not self.page:
            return None
        try:
            el = await self.page.select(
                'button[data-testid="SideNav_AccountSwitcher_Button"]', timeout=3
            )
            if el:
                full_text = el.text_all
                match = re.search(r"(@[a-zA-Z0-9_]+)", full_text)

                if match:
                    handle = match.group(1)
                    log.debug(f"Found account handle: {handle}")
                    return handle

                log.debug(f"Handle pattern not found in text: {full_text}")

        except Exception as e:
            log.debug(f"Could not read account handle: {e}")
        return None

    def save_account_metadata(self, handle: str) -> None:
        """Save or update the cookies JSON file with basic account metadata and metrics."""
        path = COOKIES_FILE
        # ensure directory exists
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
        except Exception:
            pass

        data: Dict[str, Any] = {}
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f) or {}
            except Exception as e:
                log.warning(f"Failed reading existing cookies file: {e}")

        entry = data.get(handle, {}) if isinstance(data, dict) else {}
        # preserve existing metrics if possible
        metrics = entry.get("metrics", {}) if isinstance(entry, dict) else {}
        metrics.setdefault("reposts", 0)
        metrics.setdefault("likes", 0)
        metrics.setdefault("replies", 0)
        metrics.setdefault("quotes", 0)

        entry.update(
            {
                "handle": handle,
                "auth_token": self._last_auth_token,
                "last_activity": datetime.utcnow().isoformat() + "Z",
                "metrics": metrics,
            }
        )

        if isinstance(data, dict):
            data[handle] = entry
        else:
            data = {handle: entry}

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log.info(f"Saved account metadata to {path} for handle {handle}")
        except Exception as e:
            log.error(f"Failed writing cookies file {path}: {e}")

    def increment_metric(self, metric: str, amount: int = 1) -> None:
        handle = getattr(self, "_last_handle", None)
        if not handle:
            log.debug("No handle available to increment metric")
            return

        path = COOKIES_FILE
        if not os.path.exists(path):
            log.debug("Cookies file not found when incrementing metric")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f) or {}
        except Exception as e:
            log.warning(f"Failed reading cookies file for metric increment: {e}")
            return

        entry = data.get(handle)
        if not entry:
            log.debug("No entry for handle when incrementing metric")
            return

        metrics = entry.get("metrics") or {}
        metrics.setdefault(metric, 0)
        try:
            metrics[metric] = int(metrics.get(metric, 0)) + int(amount)
        except Exception:
            metrics[metric] = 1

        entry["metrics"] = metrics
        data[handle] = entry

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log.debug(f"Incremented metric '{metric}' for {handle}")
        except Exception as e:
            log.error(f"Failed writing cookies file for metric increment: {e}")

    # --- Helper functions ---
    async def get_tweet_text(self, tweet_id: uc.Element) -> str:
        return str(tweet_id.text_all).strip().replace("\n", " ")
