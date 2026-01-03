import asyncio
import random
import nodriver as uc
from typing import List, Set, Optional
from config import (
    PROB_LIKE,
    PROB_REPOST,
    PROB_REPLY,
    PROB_QUOTE,
)
from LLM.mistral_client import MistralClient
from x_handling.x_browser import XBrowser
from utils.logger import get_logger

log = get_logger(__name__)


class UserSimulator:
    def __init__(
        self, browser: XBrowser, llm_client: MistralClient, max_actions: int = 20
    ) -> None:
        self.browser: XBrowser = browser
        self.llm: MistralClient = llm_client
        self.max_actions: int = max_actions
        # Keep track of tweets processed in this session to prevent loops
        self.processed_cache: Set[int] = set()

    async def _active_cooldown(self, duration: int) -> None:
        """
        Performs active scrolling/idling for a set duration.
        """
        if self.browser.page:
            log.debug(f"Starting active scrolling cooldown for {duration}s")
            elapsed = 0.0

            while elapsed < duration:
                try:
                    await self._random_scroll(min_pct=30, max_pct=60)
                    step = random.uniform(2.0, 5.0)
                    await asyncio.sleep(step)
                    elapsed += step
                except Exception as e:
                    log.warning(f"Error during active cooldown: {e}")
                    await asyncio.sleep(1)
                    elapsed += 1

    async def _random_scroll(self, min_pct: int = 15, max_pct: int = 40) -> None:
        try:
            if self.browser.page:
                amount = random.randint(min_pct, max_pct)
                await self.browser.page.scroll_down(amount)
                await asyncio.sleep(random.uniform(0.5, 1.2))
        except Exception:
            pass

    async def _find_new_tweet_in_view(self) -> Optional[uc.Element]:
        """
        Scans current view for any tweet NOT in the processed cache.
        Returns the element of the first new tweet found, or None.
        """
        tweet_divs: List[uc.Element] = await self.browser.collect_feed_tweets()
        
        for div in tweet_divs:
            try:
                text = await self.browser.get_tweet_text(div)
                if not text:
                    continue
                
                text_hash = hash(text)
                if text_hash not in self.processed_cache:
                    # Found a new one!
                    log.debug(f"Found new unseen tweet: {text[:40]}...")
                    return div
                
                # If seen, we just ignore it and check the next one
            except Exception:
                continue
        
        return None

    async def _refresh_page_routine(self) -> None:
        if not self.browser.page:
            return
        log.info("Refreshing page to fetch new tweets...")
        try:
            await self.browser.page.reload()
            await asyncio.sleep(random.uniform(5.0, 8.0))
            await self._random_scroll(min_pct=30, max_pct=60)
        except Exception as e:
            log.error(f"Error refreshing page: {e}")

    async def _process_tweet_item(self, target_div: uc.Element, current_iter: int) -> Optional[str]:
        # 1. Extract Text First (to cache it even if interaction fails)
        try:
            tweet_text = await self.browser.get_tweet_text(target_div)
            if not tweet_text:
                tweet_text = "UNKNOWN_TEXT"

            text_hash = hash(tweet_text)
            self.processed_cache.add(text_hash)

        except Exception as e:
            log.warning(f"Error extracting tweet text: {e}")
            return None

        # 2. Enter Tweet Detail
        try:
            # Re-verify we are in FEED before clicking?
            # We assume caller ensures FEED state.
            await self.browser.process_single_tweet(target_div, current_iter)
            
            # Wait for navigation
            await asyncio.sleep(random.uniform(2.0, 4.0))
            
            # Verify we actually landed on DETAIL
            state = await self.browser.get_current_page_state()
            if state != "DETAIL":
                log.warning(f"Failed to enter tweet detail view. Current state: {state}")
                return None
            
            # Simulate reading comments
            await self.browser.scroll_comments(scrolls=random.randint(2, 5))
            
        except Exception as e:
            log.error(f"Failed to click/enter tweet: {e}")
            return None
        
        return tweet_text

    async def _perform_random_action(self, current_iter: int, tweet_text: str) -> bool:
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
        
        return performed

    async def simulate_feed(self, token_line_index: int = 0) -> None:
        try:
            await self.browser.create_browser(index=token_line_index)
            await self.browser.goto_target()
            await asyncio.sleep(3)

            actions_done: int = 0
            consecutive_scrolls_no_new: int = 0
            MAX_SCROLLS_BEFORE_REFRESH = 5

            log.info(f"Starting simulation. Target: {self.max_actions} actions.")
            
            while actions_done < self.max_actions:
                
                # 1. State Check: Ensure we are on Feed
                await self.browser.ensure_feed_page()

                # 2. Find a Valid Tweet in View
                target_div = await self._find_new_tweet_in_view()
                
                if not target_div:
                    # No new tweets visible. Scroll down.
                    log.debug("No new tweets in current view. Scrolling...")
                    await self._random_scroll(min_pct=40, max_pct=80)
                    consecutive_scrolls_no_new += 1
                    
                    if consecutive_scrolls_no_new >= MAX_SCROLLS_BEFORE_REFRESH:
                        log.info("Can't find new tweets after multiple scrolls. Refreshing...")
                        await self._refresh_page_routine()
                        consecutive_scrolls_no_new = 0
                    
                    # Loop back to try finding again
                    await asyncio.sleep(1.0)
                    continue
                
                # Found a tweet! Reset counter
                consecutive_scrolls_no_new = 0
                current_iter = actions_done + 1

                # 3. Process the Tweet (Click -> Detail)
                tweet_text = await self._process_tweet_item(target_div, current_iter)
                if not tweet_text:
                    # Failed to enter or extract, skip logic handled in process_tweet_item
                    # It likely stayed on feed or got confused, ensure_feed_page next loop will fix
                    continue
                
                # 4. Perform Action (We are now in DETAIL view)
                try:
                    performed = await self._perform_random_action(current_iter, tweet_text)
                except Exception as e:
                    log.error(f"Error performing action: {e}")
                    performed = False

                # 5. Post-Action Cleanup
                await asyncio.sleep(random.uniform(2.0, 4.0))

                # Since we are in DETAIL (validated in step 3), we MUST go back to feed.
                # If action failed, we might still be in DETAIL, so go back is safe.
                # If we somehow got kicked to feed, ensure_feed_page next loop handles it, 
                # but let's try to be nice and click back if we think we are deeper.
                
                await self.browser.ensure_feed_page() # This handles "Go Back" intelligently now

                if performed:
                    actions_done += 1
                    cooldown = random.randint(15, 30)
                    await self._active_cooldown(cooldown) # Scroll the FEED
                else:
                    await asyncio.sleep(1.0)
                    # Just scroll past the one we entered
                    await self._random_scroll(min_pct=20, max_pct=40)

            log.info(f"Simulation completed. Actions: {actions_done}")

        except Exception as e:
            log.error(f"Simulation failed critical error: {e}")
