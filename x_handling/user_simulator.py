import asyncio
import importlib
import random
import sys
import nodriver as uc
from typing import List, Set, Optional, Dict, Any

# Only available on Windows, but user is on Windows
try:
    import msvcrt
except ImportError:
    msvcrt = None

import config
from config import (
    PROB_LIKE,
    PROB_REPOST,
    PROB_REPLY,
    PROB_QUOTE,
    PROB_LIKE_COMMENT,
    PROB_FOLLOW,
    PROB_WHO_TO_FOLLOW,
    MAX_INTERACTIONS_PER_THREAD,
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
        # Store config values as instance attributes for dynamic reloading
        self._load_config_values()

    def _load_config_values(self) -> None:
        """Load probability values from config module into instance attributes."""
        self.prob_like = config.PROB_LIKE
        self.prob_repost = config.PROB_REPOST
        self.prob_reply = config.PROB_REPLY
        self.prob_quote = config.PROB_QUOTE
        self.prob_like_comment = config.PROB_LIKE_COMMENT
        self.prob_follow = config.PROB_FOLLOW
        self.prob_who_to_follow = config.PROB_WHO_TO_FOLLOW
        self.max_interactions_per_thread = config.MAX_INTERACTIONS_PER_THREAD

    def _reload_config(self) -> None:
        """
        Reload config module and update instance probability values.
        Allows live editing of config.py during pause for debugging.
        """
        try:
            importlib.reload(config)
            self._load_config_values()
            log.info("[CONFIG] Reloaded config.py successfully!")
            log.info(f"  PROB_LIKE: {self.prob_like}")
            log.info(f"  PROB_REPOST: {self.prob_repost}")
            log.info(f"  PROB_REPLY: {self.prob_reply}")
            log.info(f"  PROB_QUOTE: {self.prob_quote}")
            log.info(f"  PROB_LIKE_COMMENT: {self.prob_like_comment}")
            log.info(f"  PROB_FOLLOW: {self.prob_follow}")
            log.info(f"  PROB_WHO_TO_FOLLOW: {self.prob_who_to_follow}")
        except Exception as e:
            log.error(f"[CONFIG] Failed to reload config: {e}")

    async def _check_debug_commands(self) -> None:
        """
        Non-blocking check for keyboard input to pause/resume/stop.
        Keys:
            p: pause simulation
            r: resume simulation (only when paused)
            s: stop simulation entirely
        """
        if not msvcrt:
            return

        try:
            if msvcrt.kbhit():
                key = msvcrt.getch().decode("utf-8", errors="ignore").lower()
                
                if key == "s":
                    log.warning("[DEBUG] STOP command received. Exiting simulation...")
                    raise KeyboardInterrupt("Stopped by user command.")
                
                elif key == "p":
                    log.warning("[DEBUG] PAUSE command received. Press 'r' to resume, 's' to stop.")
                    print("\n" + "="*50)
                    print("SIMULATION PAUSED - Press 'r' to resume, 's' to stop")
                    print("="*50 + "\n")
                    
                    while True:
                        await asyncio.sleep(0.3)
                        if msvcrt.kbhit():
                            resume_key = msvcrt.getch().decode("utf-8", errors="ignore").lower()
                            if resume_key == "r":
                                # Reload config on resume for live debugging
                                self._reload_config()
                                log.info("[DEBUG] RESUME command received. Continuing simulation...")
                                print("\n" + "="*50)
                                print("SIMULATION RESUMED")
                                print("="*50 + "\n")
                                break
                            elif resume_key == "s":
                                log.warning("[DEBUG] STOP command received during pause.")
                                raise KeyboardInterrupt("Stopped by user command.")
        except UnicodeDecodeError:
            pass  # Ignore non-UTF8 key presses

    async def _active_cooldown(self, duration: int) -> None:
        """
        Performs active scrolling/idling for a set duration.
        """
        if self.browser.page:
            log.debug(f"Starting active scrolling cooldown for {duration}s")
            elapsed = 0.0

            while elapsed < duration:
                await self._check_debug_commands()
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
                # Convert 'pct' to pixels relative to viewport height for consistency?
                # Or just treat arguments as pixel ranges if they are large.
                # The original code passed 'amount' to scroll_down which usually takes pixels? 
                # or 'steps'? nodriver scroll_down usually takes steps or distance.
                # Let's assume the previous logic meant "some amount".
                # To be safe and smooth, let's pick a pixel amount between 300 and 700.
                
                amount = random.randint(400, 800)
                await self.browser.smooth_scroll_by(amount)
                
        except Exception as e:
            log.debug(f"Random scroll error: {e}")

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
            except Exception as e:
                log.debug(f"Error processing tweet text: {e}")
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

    async def _process_tweet_item(self, target_div: uc.Element) -> Optional[str]:
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
            await self.browser.process_single_tweet(target_div)
            
            # Wait for navigation
            await asyncio.sleep(random.uniform(2.0, 4.0))
            
            # Verify we actually landed on DETAIL
            state = await self.browser.get_current_page_state()
            if state != "DETAIL":
                log.warning(f"Failed to enter tweet detail view. Current state: {state}")
                return None
            
            # Simulate reading comments and interacting
            interactions_count = 0
            # Scroll a few times to read comments
            total_scrolls = random.randint(2, 5)
            
            for _ in range(total_scrolls):
                if interactions_count >= self.max_interactions_per_thread:
                    log.debug("Max thread interactions reached. Just scrolling now.")
                
                # 1. Scroll
                await self.browser.scroll_comments(scrolls=1)
                
                # 2. Check visible comments for interactions if under limit
                if interactions_count < self.max_interactions_per_thread:
                    visible_comments = await self.browser.collect_visible_comments()
                    
                    # Shuffle to pick random ones if multiple are visible
                    if visible_comments:
                        random.shuffle(visible_comments)
                        
                        # Process a subset to avoid doing too much per scroll
                        for comment in visible_comments[:3]: 
                             if interactions_count >= self.max_interactions_per_thread:
                                 break
                             
                             # Try Like Comment
                             if random.random() < self.prob_like_comment:
                                 if await self.browser.like_comment(comment):
                                     interactions_count += 1
                                     await asyncio.sleep(random.uniform(1.0, 2.0))
                                     continue # Don't follow same user immediately if just liked?
                             
                             # Try Follow User
                             if random.random() < self.prob_follow:
                                 # We need to find the user link inside the comment
                                 # Usually it's the avatar link or name link: a[href*="/"]
                                 # Standard: User-Name or Avatar usually has href.
                                 # Let's try to find a link that looks like a profile link
                                 try:
                                     user_link = await comment.find('a[href^="/"]', best_match=True)
                                     if user_link:
                                         if await self.browser.follow_user_via_hover(user_link):
                                             interactions_count += 1
                                             await asyncio.sleep(random.uniform(1.0, 2.0))
                                 except Exception:
                                     pass
            
        except Exception as e:
            log.error(f"Failed to click/enter tweet: {e}")
            return None
        
        return tweet_text

    async def _perform_random_action(self, current_iter: int, tweet_text: str) -> bool:
        r: float = random.random()
        performed = False

        if r < self.prob_like:
            await self.browser.like_current_tweet()
            performed = True
            log.info(f"Action {current_iter}: Liked.")

        elif r < self.prob_like + self.prob_repost:
            await self.browser.repost_tweet()
            performed = True
            log.info(f"Action {current_iter}: Reposted.")

        elif r < self.prob_like + self.prob_repost + self.prob_reply:
            reply_text = await self.llm.get_response(tweet_text)
            if reply_text:
                await self.browser.comment_current_tweet(reply_text)
                performed = True
                log.info(f"Action {current_iter}: Replied.")

        elif r < self.prob_like + self.prob_repost + self.prob_reply + self.prob_quote:
            quote_text = await self.llm.get_response(tweet_text)
            if quote_text:
                await self.browser.quote_current_tweet(quote_text)
                performed = True
                log.info(f"Action {current_iter}: Quoted.")
        
        elif r < self.prob_like + self.prob_repost + self.prob_reply + self.prob_quote + self.prob_who_to_follow:
             # This action is independent of the current tweet but fits the probability model
             if await self.browser.process_who_to_follow():
                 performed = True
                 log.info(f"Action {current_iter}: Checked 'Who to Follow'.")

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
                # Check for debug commands at start of each iteration
                await self._check_debug_commands()
                
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
                    await self._check_debug_commands()
                    await asyncio.sleep(1.0)
                    continue
                
                # Found a tweet! Reset counter
                consecutive_scrolls_no_new = 0
                current_iter = actions_done + 1

                # 3. Process the Tweet (Click -> Detail)
                tweet_text = await self._process_tweet_item(target_div)
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
                await self._check_debug_commands()
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

        except KeyboardInterrupt:
            log.warning("Simulation stopped by user command.")
        except Exception as e:
            log.error(f"Simulation failed critical error: {e}")
