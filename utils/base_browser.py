import nodriver as uc
import asyncio
import random
import shutil
import os
from typing import List, Tuple, Optional, Any
from fake_useragent import UserAgent
from config import HEADLESS_BROWSER
from utils.logger import get_logger

log = get_logger(__name__)


class BaseBrowser:
    def __init__(self, headless: bool = HEADLESS_BROWSER):
        self.headless = headless
        self.ua_generator = UserAgent()
        self.browser: Optional[uc.Browser] = None
        self.user_data_dir = None
        # Default resolutions list (Width, Height)
        self.resolutions: List[Tuple[int, int]] = [
            (1920, 1080),
            # (1366, 768),
            # (1536, 864),
            # (1440, 900),
            # (1600, 900),
            # (1280, 720),
            # (800, 600),
            # (2560, 1440),
            # (3840, 2160),
        ]

        self.languages: List[str] = ["en-US", "en-GB", "fr-FR", "de-DE"]

    def __getattr__(self, name: str) -> Any:
        if self.browser and hasattr(self.browser, name):
            return getattr(self.browser, name)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'"
        )

    def _get_random_resolution(self) -> Tuple[int, int]:
        base_w, base_h = random.choice(self.resolutions)
        w = base_w + random.randint(-20, 20)
        h = base_h + random.randint(-20, 20)
        return w, h

    def _generate_browser_args(
        self, width: int, height: int, user_agent: str
    ) -> List[str]:
        return [
            f"--window-size={width},{height}",
            f"--user-agent={user_agent}",
            random.choice(["--disable-gpu", "--enable-gpu"]),
            f"--force-device-scale-factor={random.uniform(1.0, 1.25):.2f}",
            f"--renderer-process-limit={random.randint(5, 20)}",
            f"--screen-width={random.randint(1200, 1920)}",
            f"--screen-height={random.randint(800, 1080)}",
            "--disable-extensions",
        ]

    async def create_browser(self) -> uc.Browser:
        w, h = self._get_random_resolution()
        user_agent = self.ua_generator.random
        lang = random.choice(self.languages)

        args = self._generate_browser_args(w, h, user_agent)

        log.info("Starting Browser with randomized fingerprint...")
        self.browser = await uc.start(
            browser_args=args, headless=self.headless, lang=lang
        )
        return self.browser

    async def stop(self):
        if self.browser:
            try:
                self.user_data_dir = self.browser.config.user_data_dir
                self.browser.stop()
                await asyncio.sleep(1.5)
                log.debug("Browser process stopped.")
                if self.user_data_dir and os.path.exists(self.user_data_dir):
                    try:
                        shutil.rmtree(self.user_data_dir, ignore_errors=True)
                        log.debug(f"Cleaned up temp profile: {self.user_data_dir}")
                    except Exception as e:
                        log.warning(f"Could not delete temp dir: {e}")
            except Exception as e:
                log.error(f"Error during browser shutdown: {e}")
            finally:
                self.browser = None
