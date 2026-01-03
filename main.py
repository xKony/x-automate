import asyncio
import json
import os
from typing import Optional, Dict, Any
from utils.logger import get_logger
from utils.vpn_manager import VpnManager
from x_handling.x_browser import XBrowser
from x_handling.user_simulator import UserSimulator
from LLM.mistral_client import MistralClient
from config import (
    HEADLESS_BROWSER,
    AUTH_TOKENS_FILE,
    COOKIES_FILE,
    MAX_ACTIONS,
)

log = get_logger(__name__)


def _count_tokens(filepath: str) -> int:
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            tokens = [l.strip() for l in f if l.strip()]
            return len(tokens)
    except FileNotFoundError:
        log.error(f"Auth tokens file not found: {filepath}")
        return 0


def _get_start_vpn_prefs(token_index: int) -> Optional[Dict[str, Any]]:
    """
    Resolves the VPN preferences for the account at the given token index.
    It reads the token from AUTH_TOKENS_FILE, then looks for that token in COOKIES_FILE.
    """
    try:
        # 1. Get Token
        with open(AUTH_TOKENS_FILE, "r", encoding="utf-8") as f:
            tokens = [l.strip() for l in f if l.strip()]
        
        if token_index >= len(tokens):
            return None
        
        target_token = tokens[token_index]

        # 2. Find Account in Cookies JSON
        if not os.path.exists(COOKIES_FILE):
            return None

        with open(COOKIES_FILE, "r", encoding="utf-8") as f:
            cookies_data = json.load(f)
        
        # Search for token value in values
        for handle, data in cookies_data.items():
            if data.get("auth_token") == target_token:
                return data.get("vpn_preferences")
        
    except Exception as e:
        log.error(f"Error resolving VPN preferences: {e}")
    
    return None


async def main(vpn_manager: VpnManager) -> None:
    total = _count_tokens(AUTH_TOKENS_FILE)
    if total == 0:
        log.error("No auth tokens found; nothing to do.")
        return

    llm_client = MistralClient()
    # vpn_manager is now passed in

    log.info(f"Starting simulation loop for {total} account(s)")

    for idx in range(total):
        log.info(f"Processing account {idx + 1}/{total}")

        # Rotate VPN before starting browser
        try:
            prefs = _get_start_vpn_prefs(idx)
            if prefs:
                log.info(f"Found VPN preferences for account {idx + 1}: {prefs}")
            else:
                log.info(f"No specific VPN preferences found for account {idx + 1}. Using default rotation.")
            
            vpn_manager.rotate_ip(vpn_preferences=prefs)
            
            # Stabilization wait after VPN switch (rotate_ip already waits somewhat, but extra safety doesn't hurt)
            await asyncio.sleep(2) 

        except Exception as e:
            log.error(f"VPN Rotation threw an error: {e}")
            # Decide: continue or abort? We'll continue but log heavily.

        browser = XBrowser(headless=HEADLESS_BROWSER)
        simulator = UserSimulator(
            browser=browser, llm_client=llm_client, max_actions=MAX_ACTIONS
        )

        try:
            await simulator.simulate_feed(token_line_index=idx)
        except Exception as e:
            log.error(f"Simulation error for account index {idx}: {e}")
        finally:
            try:
                await browser.stop()
            except Exception:
                pass
        await asyncio.sleep(2)


if __name__ == "__main__":
    try:
        # Initialize VpnManager here to avoid asyncio loop conflicts during first-run configuration
        vpn_manager_instance = VpnManager()
        asyncio.run(main(vpn_manager_instance))
    except KeyboardInterrupt:
        log.warning("Script interrupted by user.")
        exit(0)
