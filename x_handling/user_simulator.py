import asyncio
import random
import nodriver as uc
from typing import List
from config import (
    PROB_LIKE,
    PROB_REPOST,
    PROB_REPLY,
    PROB_QUOTE,
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

    async def _random_scroll(self, min_pct: int = 15, max_pct: int = 40):
        try:
            if self.browser.page:
                # nodriver scroll_down takes an integer percentage (25 = 1/4th page)
                amount = random.randint(min_pct, max_pct)
                await self.browser.page.scroll_down(amount)
                # Small micro-pause for smooth scrolling effect
                await asyncio.sleep(random.uniform(0.5, 1.2))
        except Exception:
            pass

    async def _active_cooldown(self, duration: int):
        log.debug(f"Starting active scrolling cooldown for {duration}s")
        elapsed = 0.0

        while elapsed < duration:
            try:
                # 1. Scroll a small amount (reading behavior: 10% to 30% of screen)
                await self._random_scroll(min_pct=10, max_pct=30)

                # 2. Parse tweets to keep DOM fresh and prevent errors
                await self.browser.collect_feed_tweets()

                # 3. Wait a random 'reading' interval
                step = random.uniform(2.0, 5.0)
                await asyncio.sleep(step)

                elapsed += step
            except Exception as e:
                log.warning(f"Minor error during active cooldown: {e}")
                # Don't break the loop, just wait a bit and continue
                await asyncio.sleep(1)
                elapsed += 1

    async def simulate_feed(self, token_line_index: int = 0):
        try:
            await self.browser.create_browser(index=token_line_index)
            await self.browser.goto_target()

            # Initial scroll to load data (scroll 40% to 80% of page)
            await self._random_scroll(min_pct=40, max_pct=80)

            actions_done: int = 0
            consecutive_failures: int = 0

            log.info(f"Starting simulation. Target: {self.max_actions} actions.")

            while actions_done < self.max_actions:
                # 1. Parse current visible tweets
                tweet_divs: List[uc.Element] = await self.browser.collect_feed_tweets()

                if not tweet_divs:
                    log.warning("No tweets found. Scrolling and retrying...")
                    # Scroll significantly to find content (50% to 100% of page)
                    await self._random_scroll(min_pct=50, max_pct=100)
                    consecutive_failures += 1
                    if consecutive_failures > 5:
                        log.error(
                            "Failed to find tweets after multiple attempts. Exiting."
                        )
                        break
                    continue

                # Reset failure counter if we found tweets
                consecutive_failures = 0

                # Target the first relevant tweet found
                target_div: uc.Element = tweet_divs[0]
                current_iter = actions_done + 1

                # 2. Extract Text for LLM Context
                try:
                    tweet_text = await self.browser.get_tweet_text(target_div)
                except Exception:
                    tweet_text = ""

                # 3. Open Tweet Detail
                try:
                    await self.browser.process_single_tweet(target_div, current_iter)
                except Exception as e:
                    log.error(f"Failed to process tweet div: {e}")
                    # Scroll past this problem tweet
                    await self._random_scroll(min_pct=20, max_pct=40)
                    continue

                # 4. Determine Action based on probability
                r: float = random.random()
                performed = False

                if r < PROB_LIKE:
                    await self.browser.like_current_tweet()
                    performed = True
                    log.info(
                        f"Action {current_iter}/{self.max_actions}: Liked (r={r:.3f})."
                    )

                elif r < PROB_LIKE + PROB_REPOST:
                    await self.browser.repost_tweet()
                    performed = True
                    log.info(
                        f"Action {current_iter}/{self.max_actions}: Reposted (r={r:.3f})."
                    )

                elif r < PROB_LIKE + PROB_REPOST + PROB_REPLY:
                    reply_text = await self.llm.get_response(tweet_text)
                    if reply_text:
                        await self.browser.comment_current_tweet(reply_text)
                        performed = True
                        log.info(
                            f"Action {current_iter}/{self.max_actions}: Replied (r={r:.3f})."
                        )

                elif r < PROB_LIKE + PROB_REPOST + PROB_REPLY + PROB_QUOTE:
                    quote_text = await self.llm.get_response(tweet_text)
                    if quote_text:
                        await self.browser.quote_current_tweet(quote_text)
                        performed = True
                        log.info(
                            f"Action {current_iter}/{self.max_actions}: Quoted (r={r:.3f})."
                        )

                # Pause while looking at the tweet detail (mimic reading the replies)
                await asyncio.sleep(random.uniform(2.0, 4.5))

                # 5. Go back to feed
                await self.browser.go_back()

                # 6. Post-Action Handling
                if performed:
                    actions_done += 1

                    # Random cooldown duration
                    cooldown = random.randint(15, 45)

                    # Perform "Active" cooldown (scroll + parse)
                    await self._active_cooldown(cooldown)
                else:
                    log.debug(f"No action taken for this tweet (r={r:.3f}).")
                    # Even if no action, scroll a tiny bit (10-25%) to move to next tweet
                    await asyncio.sleep(random.uniform(1.0, 2.0))
                    await self._random_scroll(min_pct=10, max_pct=25)

            log.info(f"Simulation completed. Total actions performed: {actions_done}")

        except Exception as e:
            log.error(f"Simulation failed critical error: {e}")
