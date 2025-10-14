"""Browser automation with Playwright for taking screenshots."""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Callable, List, Optional
from contextlib import suppress

from playwright.async_api import async_playwright, Browser, Page
from .errors import NavigationError
from .models import Target, Metadata
from .config import AppConfig

logger = logging.getLogger(__name__)


class BrowserManager:
    """Manages Playwright browser instances."""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.browser: Optional[Browser] = None
        self.playwright = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.playwright = await async_playwright().start()
        
        browser_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-web-security",
            "--disable-features=VizDisplayCompositor",
        ]

        self.browser = await self.playwright.chromium.launch(
            headless=self.config.headless,
            args=browser_args,
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
    
    async def create_page(self) -> Page:
        """Create a new page with configured settings."""
        new_page_kwargs = {}
        if self.config.user_agent:
            new_page_kwargs["user_agent"] = self.config.user_agent

        page = await self.browser.new_page(**new_page_kwargs)
        
        # Set viewport
        await page.set_viewport_size({"width": 1920, "height": 1080})
        
        # Set timeout
        page.set_default_timeout(self.config.timeout_ms)
        
        return page


async def try_urls(host: str, page: Page, timeout_ms: int) -> tuple[str, int]:
    """Try HTTPS first, then HTTP fallback with timeout protection.

    Treats 2xx/3xx and 401/403 as "working" responses.
    """
    
    async def safe_goto(url: str, wait_until: str, timeout_seconds: float):
        """Navigate with timeout; ensure underlying task is cancelled and awaited on timeout.
        Prevents 'Future exception was never retrieved' warnings from asyncio.
        """
        task = asyncio.create_task(page.goto(url, wait_until=wait_until))
        try:
            return await asyncio.wait_for(task, timeout_seconds)
        except asyncio.TimeoutError:
            task.cancel()
            with suppress(Exception):
                await task
            raise
    
    async def safe_wait_for_load_state(state: str, timeout_ms: int):
        """Wait for load state with timeout; cancel properly to avoid dangling futures."""
        task = asyncio.create_task(page.wait_for_load_state(state, timeout=timeout_ms))
        try:
            return await asyncio.wait_for(task, timeout_ms / 1000.0)
        except asyncio.TimeoutError:
            task.cancel()
            with suppress(Exception):
                await task
            raise
    urls_to_try = [
        f"https://{host}",
        f"http://{host}"
    ]
    
    for url in urls_to_try:
        try:
            logger.debug(f"Trying {url}")
            
            # Use shorter timeout and don't wait for network idle
            response = await safe_goto(url, wait_until="domcontentloaded", timeout_seconds=timeout_ms / 1000.0)
            
            # Consider 2xx/3xx and 401/403 as working
            if response and (response.status < 400 or response.status in (401, 403)):
                # Wait a bit more for content to load, but with timeout
                try:
                    await safe_wait_for_load_state("networkidle", timeout_ms=5000)
                except asyncio.TimeoutError:
                    logger.debug(f"Network idle timeout for {url}, continuing anyway")
                
                return url, response.status
            
        except asyncio.TimeoutError:
            logger.debug(f"Timeout loading {url}")
            continue
        except Exception as e:
            # Handle Playwright-specific errors gracefully
            error_msg = str(e)
            if "net::ERR_ABORTED" in error_msg or "frame was detached" in error_msg:
                logger.debug(f"Connection aborted for {url} (normal for unreachable domains)")
            else:
                logger.debug(f"Failed to load {url}: {e}")
            continue
    
    # If all fail, return the last attempted URL with error status
    return urls_to_try[-1], 500


async def screenshot_target(target: Target, page: Page, config: AppConfig) -> Target:
    """Take a screenshot of a single target."""
    try:
        # Try to navigate to the target
        final_url, status_code = await try_urls(target.host, page, config.timeout_ms)
        
        # Get page title with timeout protection
        try:
            title = await asyncio.wait_for(page.title(), timeout=5.0)
        except asyncio.TimeoutError:
            title = "Title timeout"
            logger.debug(f"Title timeout for {target.host}")
        
        # Take screenshot with timeout protection
        screenshot_path = config.run_dir / "screenshots" / f"{target.host}.png"
        screenshot_path.parent.mkdir(exist_ok=True)
        
        try:
            await asyncio.wait_for(
                page.screenshot(
                    path=str(screenshot_path),
                    full_page=config.fullpage,
                ),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            logger.debug(f"Screenshot timeout for {target.host}")
            target.error = NavigationError(
                "Screenshot capture timed out",
                code="SCREENSHOT_CAPTURE_TIMEOUT"
            )
            return target
        
        # Get screenshot size
        screenshot_size = screenshot_path.stat().st_size if screenshot_path.exists() else 0
        
        # Update target metadata
        target.metadata = Metadata(
            title=title,
            status_code=status_code,
            final_url=final_url,
            screenshot_path=screenshot_path,
            screenshot_size=screenshot_size
        )
        
        logger.debug(f"Screenshot taken for {target.host}: {screenshot_path}")
        
    except Exception as e:
        logger.error(f"Failed to screenshot {target.host}: {e}")
        target.error = NavigationError(
            f"Failed to take screenshot: {e}",
            code="SCREENSHOT_FAILED"
        )
    
    return target


async def screenshot_many(
    targets: List[Target],
    config: AppConfig,
    progress_callback: Optional[Callable[[Target], None]] = None,
) -> List[Target]:
    """Take screenshots of multiple targets with concurrency control and timeout protection."""

    semaphore = asyncio.Semaphore(max(config.concurrency, 1))

    async def process_target(index: int, target: Target, browser_mgr: BrowserManager) -> tuple[int, Target]:
        async with semaphore:
            page = await browser_mgr.create_page()
            try:
                try:
                    result = await asyncio.wait_for(
                        screenshot_target(target, page, config),
                        timeout=(config.timeout_ms / 1000.0) + 10,
                    )
                except asyncio.TimeoutError:
                    logger.debug(f"Timeout taking screenshot of {target.host}")
                    target.error = NavigationError(
                        f"Screenshot timeout after {config.timeout_ms}ms",
                        code="SCREENSHOT_TIMEOUT",
                    )
                    result = target
                except asyncio.CancelledError as exc:
                    logger.debug(f"Screenshot task cancelled for {target.host}: {exc}")
                    target.error = NavigationError(
                        "Screenshot task was cancelled",
                        code="SCREENSHOT_CANCELLED",
                    )
                    result = target
                except Exception as exc:  # pylint: disable=broad-except
                    logger.error(f"Error taking screenshot of {target.host}: {exc}")
                    target.error = NavigationError(
                        f"Screenshot failed: {exc}",
                        code="SCREENSHOT_ERROR",
                    )
                    result = target
            finally:
                with suppress(Exception, asyncio.CancelledError):
                    await page.close()

        return index, result

    if not targets:
        return []

    overall_timeout = (config.timeout_ms / 1000.0 * len(targets)) + 60

    async with BrowserManager(config) as browser_mgr:
        tasks = [
            asyncio.create_task(process_target(index, target, browser_mgr))
            for index, target in enumerate(targets)
        ]

        results: List[Optional[Target]] = [None] * len(targets)

        try:
            for coro in asyncio.as_completed(tasks, timeout=overall_timeout):
                index, target = await coro
                results[index] = target
                if progress_callback:
                    progress_callback(target)
        except asyncio.TimeoutError:
            logger.error(f"Overall screenshot process timed out after {overall_timeout}s")
            for task in tasks:
                if not task.done():
                    task.cancel()

            await asyncio.gather(*tasks, return_exceptions=True)

            for idx, existing in enumerate(results):
                if existing is None:
                    timed_out_target = targets[idx]
                    timed_out_target.error = NavigationError(
                        "Screenshot process timed out",
                        code="OVERALL_TIMEOUT",
                    )
                    results[idx] = timed_out_target

        else:
            # Ensure all tasks are awaited to silence warnings
            await asyncio.gather(*tasks, return_exceptions=True)

        # Replace any None entries with originals (should not happen but safe guard)
        return [result or targets[idx] for idx, result in enumerate(results)]


if __name__ == "__main__":
    # Test code
    pass
