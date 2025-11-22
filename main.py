import asyncio
from utils.logger import get_logger

log = get_logger(__name__)


async def main():
    pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.warning("Script interrupted by user.")
        exit(0)
