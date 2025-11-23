import asyncio
from utils.logger import get_logger
from browser import XBrowser
from config import HEADLESS_BROWSER

log = get_logger(__name__)


async def main():
    x_browser = XBrowser(headless=HEADLESS_BROWSER)
    await x_browser.create_browser(0)
    x_browser.target = await x_browser.get("https://x.com/")
    await x_browser.find_and_click("accept all")
    await asyncio.sleep(100)
    pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("Script interrupted by user.")
        exit(0)
