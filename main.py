import asyncio
import os
from utils.logger import get_logger
from x_handling.x_browser import XBrowser
from x_handling.user_simulator import UserSimulator
from LLM.mistral_client import Mistral_Client
from config import (
    HEADLESS_BROWSER,
    AUTH_TOKENS_FILE,
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


async def main():
    total = _count_tokens(AUTH_TOKENS_FILE)
    if total == 0:
        log.error("No auth tokens found; nothing to do.")
        return

    llm_client = Mistral_Client()

    log.info(f"Starting simulation loop for {total} account(s)")

    for idx in range(total):
        log.info(f"Processing account {idx + 1}/{total}")

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
        asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("Script interrupted by user.")
        exit(0)
