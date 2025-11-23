import asyncio
from utils.logger import get_logger
from x_handling.browser import XBrowser
from config import HEADLESS_BROWSER

log = get_logger(__name__)


async def main():
    x_browser = XBrowser(headless=HEADLESS_BROWSER)
    await x_browser.create_browser(0)
    x_browser.page = await x_browser.goto_target()
    await asyncio.sleep(100)
    pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("Script interrupted by user.")
        exit(0)
