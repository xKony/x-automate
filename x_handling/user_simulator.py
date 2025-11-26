import asyncio
import random
import nodriver as uc
from typing import List, Set
from config import (
    PROB_LIKE,
    PROB_REPOST,
    PROB_REPLY,
    PROB_QUOTE,
    PROB_PAGE_REFRESH,  # Make sure to add this to your config.py (e.g., 0.05)
)
from LLM.mistral_client import Mistral_Client
from x_handling.x_browser import XBrowser
from utils.logger import get_logger

log = get_logger(__name__)


class UserSimulator:
    def __init__(
        self, browser: XBrowser, llm_client: Mistral_Client, max_actions: int = 20
    ):
        self.browser: XBrowser = browser
        self.llm: Mistral_Client = llm_client
        self.max_actions: int = max_actions
        # Keep track of tweets processed in this session to prevent loops
        self.processed_cache: Set[int] = set()

    async def _random_scroll(self, min_pct: int = 15, max_pct: int = 40):
        try:
            if self.browser.page:
                amount = random.randint(min_pct, max_pct)
                await self.browser.page.scroll_down(amount)
                await asyncio.sleep(random.uniform(0.5, 1.2))
        except Exception:
            pass

    async def _active_cooldown(self, duration: int):
        if self.browser.page:
            log.debug(f"Starting active scrolling cooldown for {duration}s")
            elapsed = 0.0

            while elapsed < duration:
                try:
                    await self._random_scroll(min_pct=30, max_pct=60)

                    # Check for randomness to refresh page during long cooldowns
                    if random.random() < (PROB_PAGE_REFRESH / 2):
                        log.info("Random page refresh triggered during cooldown.")
                        await self.browser.page.reload()
                        await asyncio.sleep(5)
                        await self._random_scroll(min_pct=20, max_pct=50)

                    # Parse tweets to keep DOM fresh
                    await self.browser.collect_feed_tweets()

                    step = random.uniform(2.0, 5.0)
                    await asyncio.sleep(step)

                    elapsed += step
                except Exception as e:
                    log.warning(f"Minor error during active cooldown: {e}")
                    await asyncio.sleep(1)
                    elapsed += 1

    async def simulate_feed(self, token_line_index: int = 0):
        try:
            await self.browser.create_browser(index=token_line_index)
            await self.browser.goto_target()

            # Initial scroll
            await self._random_scroll(min_pct=40, max_pct=80)

            actions_done: int = 0
            consecutive_failures: int = 0

            log.info(f"Starting simulation. Target: {self.max_actions} actions.")
            if self.browser.page:
                while actions_done < self.max_actions:

                    if random.random() < PROB_PAGE_REFRESH:
                        log.info("Refreshing page to fetch new tweets...")
                        await self.browser.page.reload()
                        # Wait for load
                        await asyncio.sleep(random.uniform(4.0, 7.0))
                        # Initial scroll after refresh
                        await self._random_scroll(min_pct=40, max_pct=80)
                        # Clear cache if you want to allow re-interaction after refresh,
                        # OR keep it to strictly avoid duplicates. Keeping it is safer.
                        continue

                    # 1. Parse current visible tweets
                    tweet_divs: List[uc.Element] = (
                        await self.browser.collect_feed_tweets()
                    )

                    if not tweet_divs:
                        log.warning("No tweets found. Scrolling...")
                        await self._random_scroll(min_pct=50, max_pct=100)
                        consecutive_failures += 1
                        if consecutive_failures > 5:
                            log.error("Failed to find tweets. Exiting.")
                            break
                        continue

                    consecutive_failures = 0

                    # Target the first tweet
                    target_div: uc.Element = tweet_divs[0]
                    current_iter = actions_done + 1

                    # 2. Extract Text and Check History
                    try:
                        tweet_text = await self.browser.get_tweet_text(target_div)
                        if not tweet_text:
                            tweet_text = "UNKNOWN_TEXT"

                        # Create a simple hash of the text to use as an ID
                        text_hash = hash(tweet_text)

                        # --- LOGIC: Check if already processed ---
                        if text_hash in self.processed_cache:
                            log.debug(
                                "Tweet already processed in this session. Skipping."
                            )
                            # Scroll past it
                            await self._random_scroll(min_pct=20, max_pct=40)
                            continue

                        # Add to cache
                        self.processed_cache.add(text_hash)

                    except Exception as e:
                        log.warning(f"Error extracting tweet text: {e}")
                        tweet_text = ""

                    # 3. Open Tweet Detail
                    try:
                        await self.browser.process_single_tweet(
                            target_div, current_iter
                        )
                    except Exception as e:
                        log.error(f"Failed to process tweet div: {e}")
                        await self._random_scroll(min_pct=20, max_pct=40)
                        continue

                    # 4. Determine Action
                    r: float = random.random()
                    performed = False

                    if r < PROB_LIKE:
                        await self.browser.like_current_tweet()
                        performed = True
                        log.info(f"Action {current_iter}: Liked.")

                    elif r < PROB_LIKE + PROB_REPOST:
                        await self.browser.repost_tweet()
                        performed = True
                        log.info(f"Action {current_iter}: Reposted.")

                    elif r < PROB_LIKE + PROB_REPOST + PROB_REPLY:
                        reply_text = await self.llm.get_response(tweet_text)
                        if reply_text:
                            await self.browser.comment_current_tweet(reply_text)
                            performed = True
                            log.info(f"Action {current_iter}: Replied.")

                    elif r < PROB_LIKE + PROB_REPOST + PROB_REPLY + PROB_QUOTE:
                        quote_text = await self.llm.get_response(tweet_text)
                        if quote_text:
                            await self.browser.quote_current_tweet(quote_text)
                            performed = True
                            log.info(f"Action {current_iter}: Quoted.")

                    # Pause while looking at tweet
                    await asyncio.sleep(random.uniform(2.0, 4.5))

                    # 5. Go back to feed
                    await self.browser.go_back()

                    # 6. Post-Action Handling
                    if performed:
                        actions_done += 1
                        cooldown = random.randint(15, 45)
                        await self._active_cooldown(cooldown)
                    else:
                        log.debug("No action taken.")
                        await asyncio.sleep(random.uniform(1.0, 2.0))
                        # Scroll past the tweet we just looked at but didn't touch
                        await self._random_scroll(min_pct=15, max_pct=30)

                log.info(f"Simulation completed. Actions: {actions_done}")

        except Exception as e:
            log.error(f"Simulation failed critical error: {e}")
