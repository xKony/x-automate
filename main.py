import asyncio
import os
from utils.logger import get_logger
from x_handling.x_browser import XBrowser
from config import HEADLESS_BROWSER, AUTH_TOKENS_FILE

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

    log.info(f"Starting loop for {total} account(s)")

    for idx in range(total):
        log.info(f"Processing account {idx + 1}/{total}")
        browser = XBrowser(headless=HEADLESS_BROWSER)
        try:
            await browser.create_browser(idx)
            browser.page = await browser.goto_target()
            # small stabilization pause
            await asyncio.sleep(3)
            handle = await browser.get_account_handle()
            if handle:
                print(handle)
        except Exception as e:
            log.error(f"Error processing account index {idx}: {e}")
        finally:
            try:
                await browser.stop()
            except Exception:
                pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("Script interrupted by user.")
        exit(0)
