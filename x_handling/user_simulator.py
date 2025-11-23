import os
import asyncio
import random
from typing import Optional
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
        self.browser = browser
        self.llm = llm_client
        self.max_actions = max_actions

    async def simulate_feed(
        self, token_line_index: int = 0, max_tweets: Optional[int] = None
    ):
        try:
            await self.browser.create_browser(index=token_line_index)
            await self.browser.goto_target()

            tweet_divs = await self.browser.collect_feed_tweets()
            if not tweet_divs:
                log.info("No tweets found in feed to simulate.")
                return

            actions_done = 0
            for i, div in enumerate(tweet_divs, start=1):
                if max_tweets and i > max_tweets:
                    break

                # open tweet detail
                await self.browser.process_single_tweet(div, i)

                # pick one action per tweet according to probabilities
                r = random.random()
                performed = False

                if r < PROB_LIKE:
                    await self.browser.like_current_tweet()
                    performed = True
                    log.debug(f"Tweet {i}: Liked (r={r:.3f}).")
                elif r < PROB_LIKE + PROB_REPOST:
                    await self.browser.repost_tweet()
                    performed = True
                    log.debug(f"Tweet {i}: Reposted (r={r:.3f}).")
                elif r < PROB_LIKE + PROB_REPOST + PROB_REPLY:
                    # generate reply text from LLM
                    reply_text = await self.llm.get_response()
                    if reply_text:
                        await self.browser.comment_current_tweet(reply_text)
                        performed = True
                        log.debug(f"Tweet {i}: Replied (r={r:.3f}).")
                elif r < PROB_LIKE + PROB_REPOST + PROB_REPLY + PROB_QUOTE:
                    quote_text = await self.llm.get_response()
                    if quote_text:
                        await self.browser.quote_current_tweet(quote_text)
                        performed = True
                        log.debug(f"Tweet {i}: Quoted (r={r:.3f}).")

                # small human-like pause
                await asyncio.sleep(random.uniform(0.5, 2.0))

                # go back to feed
                await self.browser.go_back()

                if performed:
                    actions_done += 1
                if actions_done >= self.max_actions:
                    log.info("Reached maximum actions for this simulation run.")
                    break

            log.info(f"Simulation completed. Actions performed: {actions_done}")

        except Exception as e:
            log.error(f"Simulation failed: {e}")
