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
        except Exception as e:
            log.debug(f"Non-fatal error getting account handle: {e}")
        return self.page

    async def get_current_page_state(self) -> str:
        """
        Determines the current state of the browser page.
        Returns: 'FEED', 'DETAIL', or 'UNKNOWN'
        """
        if not self.page:
            return "UNKNOWN"
        
        try:
            # Check URL first (fastest)
            # nodriver might not always update 'msg' or 'url' property instantly, but it often does.
            # We can also check for specific elements.
            
            # Heuristic 1: URL inspection if possible (implementation specific to nodriver version)
            # For now, let's rely on element presence which is more robust for checking "view" state.
            
            # Check for Tweet Detail specific element (e.g. the main inline reply box)
            # 'div[data-testid="tweetTextarea_0"]' usually exists on detail pages (and sometimes home if composed?)
            # But the "Back" button "header" is a good indicator for Detail view on mobile/desktop often?
            # Actually, '/status/' in the URL is the best bet if we can get it.
            
            # Current nodriver usage: self.page.target.url might differ.
            # Let's try to fetch a known element unique to feed vs detail.
            
            # Feed usually has the "What is happening?!" compose box at top (on desktop).
            # Detail has the tweet focused.
            
            # Best reliable way: Check if URL contains "/status/"
            current_url = await self.page.evaluate("window.location.href")
            if "/status/" in current_url:
                return "DETAIL"
            elif "home" in current_url or "x.com" == current_url.strip("/"):
                return "FEED"
            
            return "UNKNOWN"

        except Exception as e:
            log.warning(f"Error checking page state: {e}")
            return "UNKNOWN"

    async def ensure_feed_page(self) -> None:
        """
        Ensures the browser is on the main feed page.
        If in DETAIL, goes back. If UNKNOWN, navigates to home.
        """
        state = await self.get_current_page_state()
        if state == "FEED":
            return
        
        if state == "DETAIL":
            log.info("Currently in DETAIL view. Going back to feed.")
            await self.go_back()
            # Double check
            await asyncio.sleep(2)
            if await self.get_current_page_state() == "FEED":
                return
        
        # Fallback: Force navigate
        log.info("State mismatch or unknown. Forcing navigation to Home.")
        await self.goto_target(X_URL)


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

    async def process_single_tweet(self, div: uc.Element, index: int = 0) -> None:
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

    # --- Advanced Navigation ---
    async def smart_scroll_to(self, element: uc.Element) -> None:
        """
        Scrolls the element into view using native JS smooth scroll.
        Centers the element to ensure visibility.
        """
        if not element or not self.page:
            return
        try:
            # Applying scrollIntoView with block: 'center' usually handles both up and down directions.
            await element.apply(
                "this.scrollIntoView({behavior: 'smooth', block: 'center', inline: 'nearest'})"
            )
            # Random "eye-tracking" delay
            await asyncio.sleep(random.uniform(0.5, 1.2))
        except Exception as e:
            log.debug(f"Smart scroll failed: {e}")
            # Fallback
            try:
                await element.scroll_into_view()
            except Exception as e:
                log.debug(f"Smart scroll fallback failed: {e}")

    async def scroll_comments(self, scrolls: int = 3) -> None:
        """
        Performs smooth gradual scrolls to read comments/replies.
        """
        if not self.page:
            return
        
        log.info("Browsing comments section...")
        for _ in range(scrolls):
            try:
                # Random scroll amount
                amount = random.randint(300, 600)
                await self.page.evaluate(f"window.scrollBy({{top: {amount}, behavior: 'smooth'}})")
                await asyncio.sleep(random.uniform(1.5, 3.0))
            except Exception as e:
                log.debug(f"Comment scroll error: {e}")
                break

    async def collect_visible_comments(self) -> List[uc.Element]:
        """
        Collects visible comment/reply tweets from the current view.
        We look for 'article' tags or divs with specific testids that represent replies.
        Detailed view replies usually have data-testid="tweet".
        """
        if not self.page:
            return []
        try:
            # "tweet" testid is used for both main tweet and replies in the thread list
            # We might want to filter out the main tweet if possible, but the main tweet is usually
            # at the top and might be scrolled past.
            comments = await self.page.select_all('article[data-testid="tweet"]')
            
            # Simple visibility check or coordinate check could be added if needed,
            # but select_all returns what's in DOM (nodriver might return all).
            # We'll rely on the caller to pick ones that look like replies.
            return comments
        except Exception as e:
            log.debug(f"Error collecting comments: {e}")
            return []

    async def smooth_scroll_by(self, amount: int) -> None:
        """
        Scrolls the window by a specific amount using native smooth behavior.
        """
        if not self.page:
            return
        try:
             await self.page.evaluate(f"window.scrollBy({{top: {amount}, behavior: 'smooth'}})")
             # Wait a bit for the scroll to actually happen
             await asyncio.sleep(random.uniform(0.8, 1.5))
        except Exception as e:
            log.debug(f"Smooth scroll failed: {e}")

    async def like_comment(self, comment_element: uc.Element) -> bool:
        """
        Likes a specific comment element.
        Uses multiple selector fallbacks for robustness.
        """
        try:
            # Try multiple selectors - X.com structure varies
            like_btn = None
            selectors = [
                'button[data-testid="like"]',
                'div[data-testid="like"]',
                '[data-testid="like"]',
            ]
            
            for selector in selectors:
                try:
                    like_btn = await comment_element.query_selector(selector)
                    if like_btn:
                        log.debug(f"Found like button with selector: {selector}")
                        break
                except Exception:
                    continue
            
            if not like_btn:
                log.debug("Like button not found in comment element")
                return False
            
            # Check if already liked (button might have different state)
            try:
                aria_pressed = await like_btn.apply("return this.getAttribute('aria-pressed')")
                if aria_pressed == "true":
                    log.debug("Comment already liked, skipping")
                    return False
            except Exception:
                pass  # Continue if we can't check state
            
            # STRICT SCROLL before interaction
            await self.smart_scroll_to(like_btn)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await like_btn.click()
            log.info("Action: Liked a comment.")
            try:
                self.increment_metric("likes")
            except Exception as e:
                log.debug(f"Failed to increment like metric: {e}")
            return True
            
        except Exception as e:
            log.debug(f"Failed to like comment: {e}")
        return False

    async def follow_user_via_hover(self, user_element: uc.Element) -> bool:
        """
        Hovers over a user link/element to trigger the hover card, then clicks Follow.
        """
        if not self.page:
            return False
        
        try:
            # 1. Scroll and Hover
            await self.smart_scroll_to(user_element)
            await asyncio.sleep(random.uniform(0.5, 1.0))
            
            # nodriver mouse move to trigger hover
            await user_element.mouse_move()
            log.debug("Hovering over user element...")
            
            # 2. Wait for Hover Card to appear
            await asyncio.sleep(random.uniform(2.0, 3.5))
            
            # X.com uses capital H in "HoverCard" (verified via live DOM inspection)
            hover_card = None
            hover_selectors = [
                'div[data-testid="HoverCard"]',
                '[data-testid="HoverCard"]',
                'div[data-testid="hoverCard"]',  # Fallback for older/different versions
                '[data-testid="hoverCardParent"]',
            ]
            
            for selector in hover_selectors:
                try:
                    hover_card = await self.page.select(selector, timeout=2)
                    if hover_card:
                        log.debug(f"Found hover card with selector: {selector}")
                        break
                except Exception:
                    continue
            
            if not hover_card:
                log.debug("Hover card did not appear after waiting.")
                return False
            
            # 3. Find Follow Button inside card
            follow_btn = None
            follow_selectors = [
                'button[aria-label^="Follow"]',
                '[data-testid*="follow"]',
                'button[data-testid*="follow"]',
            ]
            
            for selector in follow_selectors:
                try:
                    follow_btn = await hover_card.query_selector(selector)
                    if follow_btn:
                        log.debug(f"Found follow button with selector: {selector}")
                        break
                except Exception:
                    continue
            
            if not follow_btn:
                log.debug("Follow button not found in hover card.")
                return False
            
            # Check if already following
            txt = follow_btn.text_all.lower() if follow_btn.text_all else ""
            if "following" in txt or "unfollow" in txt:
                log.debug("Already following user.")
                return False

            # 4. Click Follow
            await self.smart_scroll_to(follow_btn)
            await asyncio.sleep(random.uniform(0.5, 1.2))
            await follow_btn.click()
            log.info("Action: Followed user via hover.")
            try:
                self.increment_metric("follows")
            except Exception as e:
                log.debug(f"Failed to increment follow metric: {e}")
            return True
            
        except Exception as e:
            log.debug(f"Hover follow failed: {e}")
        
        return False

    async def process_who_to_follow(self) -> bool:
        """
        Checks the 'Who to follow' sidebar and follows a random user.
        """
        if not self.page:
            return False
            
        try:
            # Try multiple selectors for the sidebar section
            aside = None
            sidebar_selectors = [
                'aside[aria-label="Who to follow"]',
                '[aria-label="Who to follow"]',
                'section[aria-label*="follow"]',
                'div[data-testid="sidebarColumn"] aside',
            ]
            
            for selector in sidebar_selectors:
                try:
                    aside = await self.page.select(selector, timeout=2)
                    if aside:
                        log.debug(f"Found 'Who to follow' section with selector: {selector}")
                        break
                except Exception:
                    continue
            
            if not aside:
                log.debug("'Who to follow' sidebar section not found.")
                return False
            
            # Find follow buttons within this aside
            buttons = []
            button_selectors = [
                'button[aria-label^="Follow"]',
                '[data-testid*="follow"]',
                'button[data-testid*="follow"]',
            ]
            
            for selector in button_selectors:
                try:
                    found_buttons = await aside.query_selector_all(selector)
                    if found_buttons:
                        buttons.extend(found_buttons)
                except Exception:
                    continue
            
            # Filter to only "Follow" buttons (not "Following")
            valid_buttons = []
            for btn in buttons:
                try:
                    txt = btn.text_all.lower() if btn.text_all else ""
                    if "following" not in txt and "unfollow" not in txt:
                        valid_buttons.append(btn)
                except Exception:
                    continue
            
            if not valid_buttons:
                log.debug("No valid 'Follow' buttons found in sidebar.")
                return False
            
            target_btn = random.choice(valid_buttons)
            
            await self.smart_scroll_to(target_btn)
            await asyncio.sleep(random.uniform(1.0, 2.0))
            await target_btn.click()
            
            log.info("Action: Followed a user from 'Who to follow'.")
            try:
                self.increment_metric("follows")
            except Exception as e:
                log.debug(f"Failed to increment follow metric: {e}")
            return True
                
        except Exception as e:
            log.debug(f"Who-to-follow action failed: {e}")
            
        return False


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
                    # Realistic Interaction Sequence
                    await self.smart_scroll_to(like_btn)
                    
                    # Think time / Hesitation
                    await asyncio.sleep(random.uniform(1.0, 3.0))
                    
                    await like_btn.click()
                    log.info("Action: Liked tweet.")
                    
                    # Post-action micro-pause
                    await asyncio.sleep(random.uniform(0.5, 1.5))
                    
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
                    await self.smart_scroll_to(retweet_menu_btn)
                    await asyncio.sleep(random.uniform(1.0, 2.5))
                    await retweet_menu_btn.click()
                    
                    await asyncio.sleep(0.5)
                    confirm_btn = await self.page.select(
                        'div[data-testid="retweetConfirm"]', timeout=3
                    )
                    if confirm_btn:
                        await asyncio.sleep(random.uniform(0.8, 1.5))
                        await confirm_btn.click()
                        log.info("Action: Reposted tweet.")
                        await asyncio.sleep(random.uniform(0.5, 1.5))
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
        """
        Reply to the current tweet using the Reply button flow.
        Steps:
        1. Click the Reply button (aria-label="Reply")
        2. Wait for the reply modal/dialog to load
        3. Find the textarea and type the reply
        4. Click the submit button (data-testid="tweetButton")
        """
        if not isinstance(self.page, uc.Tab):
            return False
            
        try:
            # 1. Find and click the Reply button
            reply_btn = None
            reply_selectors = [
                'button[aria-label="Reply"]',
                '[aria-label="Reply"]',
                'button[data-testid="reply"]',
                '[data-testid="reply"]',
            ]
            
            for selector in reply_selectors:
                try:
                    reply_btn = await self.page.select(selector, timeout=3)
                    if reply_btn:
                        log.debug(f"Found Reply button with selector: {selector}")
                        break
                except Exception:
                    continue
            
            if not reply_btn:
                log.debug("Reply button not found on page")
                return False
            
            # Click the Reply button
            await self.smart_scroll_to(reply_btn)
            await asyncio.sleep(random.uniform(0.5, 1.5))
            await reply_btn.click()
            log.debug("Clicked Reply button, waiting for modal...")
            
            # 2. Wait for the reply modal/dialog to load (X.com is laggy)
            await asyncio.sleep(random.uniform(2.5, 4.0))
            
            # 3. Find the textarea in the modal
            input_area = None
            input_selectors = [
                'div[data-testid="tweetTextarea_0"]',
                '[data-testid="tweetTextarea_0"]',
                'div[role="textbox"]',
                '[contenteditable="true"]',
            ]
            
            for selector in input_selectors:
                try:
                    input_area = await self.page.select(selector, timeout=3)
                    if input_area:
                        log.debug(f"Found input area with selector: {selector}")
                        break
                except Exception:
                    continue
            
            if not input_area:
                log.debug("Reply input area not found in modal")
                return False
            
            # Click to focus and type
            await input_area.click()
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await input_area.send_keys(text)
            log.debug(f"Typed reply text: {text[:30]}...")
            
            # Wait for review (simulating human behavior)
            await asyncio.sleep(random.uniform(1.5, 3.0))
            
            # 4. Find and click the submit button
            post_btn = None
            post_selectors = [
                'button[data-testid="tweetButton"]',
                '[data-testid="tweetButton"]',
                'button[data-testid="tweetButtonInline"]',
            ]
            
            for selector in post_selectors:
                try:
                    post_btn = await self.page.select(selector, timeout=3)
                    if post_btn:
                        log.debug(f"Found post button with selector: {selector}")
                        break
                except Exception:
                    continue
            
            if not post_btn:
                log.debug("Post/Reply button not found")
                return False
            
            await self.smart_scroll_to(post_btn)
            await asyncio.sleep(random.uniform(0.5, 1.0))
            await post_btn.click()
            log.info("Action: Replied to tweet.")
            
            # Wait for post to complete
            await asyncio.sleep(random.uniform(1.5, 2.5))
            
            try:
                self.increment_metric("replies")
            except Exception as e:
                log.debug(f"Failed to increment reply metric: {e}")
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
                    await self.smart_scroll_to(retweet_menu_btn)
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                    await retweet_menu_btn.click()
                    await asyncio.sleep(0.5)
                    
                    # 2. Click "Quote" from the dropdown
                    quote_btn = await self.page.select(
                        'a[href="/compose/post"]', timeout=3
                    )
                    if quote_btn:
                        await quote_btn.click()
                        await asyncio.sleep(1.5)

                        # 3. Type text
                        # Focus input area
                        input_area: uc.Element = await self.page.select(
                            'div[data-testid="tweetTextarea_0"]', timeout=3
                        )
                        if input_area:
                            await input_area.click()
                            await asyncio.sleep(random.uniform(0.5, 1.0))
                            await input_area.send_keys(text)
                            await asyncio.sleep(random.uniform(1.5, 3.0))

                            # 4. Click Post
                            post_btn = await self.page.select(
                                'button[data-testid="tweetButton"]', timeout=3
                            )
                            if post_btn:
                                await self.smart_scroll_to(post_btn)
                                await asyncio.sleep(random.uniform(0.5, 1.5))
                                await post_btn.click()
                                log.info("Action: Quoted tweet.")
                                await asyncio.sleep(random.uniform(1.0, 2.0))
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
        
        # Method 1: Check Account Switcher Button (Text parsing)
        try:
            el = await self.page.select(
                'button[data-testid="SideNav_AccountSwitcher_Button"]', timeout=3
            )
            if el:
                full_text = el.text_all
                match = re.search(r"(@[a-zA-Z0-9_]+)", full_text)

                if match:
                    handle = match.group(1)
                    log.debug(f"Found account handle (Method 1): {handle}")
                    return handle

                log.debug(f"Handle pattern not found in text: {full_text}")

        except Exception as e:
            log.debug(f"Method 1 (AccountSwitcher) failed: {e}")

        # Method 2: Check Profile Link in Sidebar (Href parsing)
        try:
            profile_link = await self.page.select(
                'a[data-testid="AppTabBar_Profile_Link"]', timeout=3
            )
            if profile_link:
                # Use JS execution to robustly get the href attribute
                href = await profile_link.apply("return this.getAttribute('href')")
                if href:
                     # href usually looks like "https://x.com/username" or "/username"
                     # We want "username" and prepend @
                     
                     # Remove trailing slashes
                     href = href.rstrip("/")
                     parts = href.split("/")
                     if parts:
                         username = parts[-1]
                         if username and username.lower() not in ["home", "explore", "notifications"]:
                             handle = f"@{username}"
                             log.debug(f"Found account handle (Method 2): {handle}")
                             return handle
        except Exception as e:
            log.debug(f"Method 2 (ProfileLink) failed: {e}")

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
