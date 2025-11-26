import asyncio
import random
import nodriver as uc
from typing import Optional, List, Any
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

    async def _random_scroll(self, min_px: int = 10, max_px: int = 20):
        try:
            if self.browser.page:
                amount = random.randint(min_px, max_px)
                await self.browser.page.scroll_down(amount)
                await asyncio.sleep(random.uniform(0.7, 1.5))
        except Exception:
            pass

    async def simulate_feed(self, token_line_index: int = 0):
        try:
            await self.browser.create_browser(index=token_line_index)
            await self.browser.goto_target()

            # Initial scroll to load data
            await self._random_scroll()

            actions_done: int = 0
            consecutive_failures: int = 0

            log.info(f"Starting simulation. Target: {self.max_actions} actions.")

            while actions_done < self.max_actions:
                # 1. Parse current visible tweets
                tweet_divs: List[uc.Element] = await self.browser.collect_feed_tweets()

                if not tweet_divs:
                    log.warning("No tweets found. Scrolling and retrying...")
                    await self._random_scroll()
                    consecutive_failures += 1
                    if consecutive_failures > 5:
                        log.error(
                            "Failed to find tweets after multiple attempts. Exiting."
                        )
                        break
                    continue

                # Reset failure counter if we found tweets
                consecutive_failures = 0

                target_div: uc.Element = tweet_divs[0]

                current_iter = actions_done + 1

                try:
                    # Passing current_iter just for logging consistency within the method if needed
                    await self.browser.process_single_tweet(target_div, current_iter)
                except Exception as e:
                    log.error(f"Failed to process tweet div: {e}")
                    await self._random_scroll()
                    continue

                # 4. Determine Action based on probability
                r: float = random.random()
                performed = False

                # Cumulative probability check
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
                    reply_text = await self.llm.get_response(
                        self.browser.get_tweet_text(target_div)
                    )
                    if reply_text:
                        await self.browser.comment_current_tweet(reply_text)
                        performed = True
                        log.info(
                            f"Action {current_iter}/{self.max_actions}: Replied (r={r:.3f})."
                        )

                elif r < PROB_LIKE + PROB_REPOST + PROB_REPLY + PROB_QUOTE:
                    quote_text = await self.llm.get_response(
                        self.browser.get_tweet_text(target_div)
                    )
                    if quote_text:
                        await self.browser.quote_current_tweet(quote_text)
                        performed = True
                        log.info(
                            f"Action {current_iter}/{self.max_actions}: Quoted (r={r:.3f})."
                        )

                # Pause while looking at the tweet
                await asyncio.sleep(random.uniform(1.5, 3.5))

                # 5. Go back to feed
                await self.browser.go_back()

                # 6. Post-Action Handling
                if performed:
                    actions_done += 1
                    # Longer cooldown after an actual action
                    cooldown = random.randint(5, 30)
                    log.debug(f"Action performed. Cooldown: {cooldown}s")
                    await asyncio.sleep(cooldown)
                else:
                    log.debug(f"No action taken for this tweet (r={r:.3f}). Moving on.")
                    # Short pause if we just looked and didn't touch
                    await asyncio.sleep(random.uniform(1.0, 2.0))

                # 7. CRITICAL: Scroll down to ensure we parse *new* tweets in the next iteration
                # If we don't scroll, collect_feed_tweets might return the same tweet we just processed.
                await self._random_scroll(10, 30)

            log.info(f"Simulation completed. Total actions performed: {actions_done}")

        except Exception as e:
            log.error(f"Simulation failed critical error: {e}")
