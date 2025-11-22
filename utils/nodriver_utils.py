import nodriver as uc
import random
from typing import List, Tuple
from fake_useragent import UserAgent
from config import HEADLESS_BROWSER


class Nodriver_Utils:
    def __init__(self, headless: bool = HEADLESS_BROWSER):
        self.headless = headless
        self.ua_generator = UserAgent()

        # Default resolutions list (Width, Height)
        self.resolutions: List[Tuple[int, int]] = [
            (1920, 1080),
            (1366, 768),
            (1536, 864),
            (1440, 900),
            (1600, 900),
            (1280, 720),
            (800, 600),
            (2560, 1440),
            (3840, 2160),
        ]

        self.languages: List[str] = ["en-US", "en-GB", "fr-FR", "de-DE"]

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
            f"--force-device-scale-factor={random.uniform(1.0, 1.5):.2f}",
            f"--renderer-process-limit={random.randint(5, 20)}",
            f"--screen-width={random.randint(1200, 2560)}",
            f"--screen-height={random.randint(800, 1440)}",
            "--disable-extensions",
        ]

    async def create_driver(self) -> uc.Browser:
        w, h = self._get_random_resolution()
        user_agent = self.ua_generator.random
        lang = random.choice(self.languages)
        browser_args = self._generate_browser_args(w, h, user_agent)
        browser = await uc.start(
            browser_args=browser_args, headless=self.headless, lang=lang
        )

        return browser
