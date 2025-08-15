"""Browser automation with Playwright for taking screenshots."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from contextlib import suppress
from typing import List, Optional
from urllib.parse import urljoin

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
            "--disable-features=VizDisplayCompositor"
        ]
        
        if self.config.proxy:
            browser_args.append(f"--proxy-server={self.config.proxy}")
        
        self.browser = await self.playwright.chromium.launch(
            headless=True,
            args=browser_args
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
        page = await self.browser.new_page()
        
        # Set user agent
        await page.set_extra_http_headers({
            "User-Agent": self.config.user_agent
        })
        
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
                    full_page=config.fullpage
                ),
                timeout=10.0  # 10 second timeout for screenshot
            )
        except asyncio.TimeoutError:
            logger.warning(f"Screenshot timeout for {target.host}")
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
        
        logger.info(f"Screenshot taken for {target.host}: {screenshot_path}")
        
    except Exception as e:
        logger.error(f"Failed to screenshot {target.host}: {e}")
        target.error = NavigationError(
            f"Failed to take screenshot: {e}",
            code="SCREENSHOT_FAILED"
        )
    
    return target


async def screenshot_many(targets: List[Target], config: AppConfig) -> List[Target]:
    """Take screenshots of multiple targets with concurrency control and timeout protection."""
    semaphore = asyncio.Semaphore(config.concurrency)
    
    async def screenshot_with_semaphore(target: Target) -> Target:
        async with semaphore:
            async with BrowserManager(config) as browser_mgr:
                page = await browser_mgr.create_page()
                try:
                    # Add timeout protection for each individual screenshot
                    return await asyncio.wait_for(
                        screenshot_target(target, page, config),
                        timeout=(config.timeout_ms / 1000.0) + 10  # Add 10 seconds buffer
                    )
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout taking screenshot of {target.host}")
                    target.error = NavigationError(
                        f"Screenshot timeout after {config.timeout_ms}ms",
                        code="SCREENSHOT_TIMEOUT"
                    )
                    return target
                except Exception as e:
                    logger.error(f"Error taking screenshot of {target.host}: {e}")
                    target.error = NavigationError(
                        f"Screenshot failed: {e}",
                        code="SCREENSHOT_ERROR"
                    )
                    return target
                finally:
                    await page.close()
    
    # Process targets concurrently with overall timeout
    tasks = [screenshot_with_semaphore(target) for target in targets]
    
    try:
        # Add overall timeout to prevent indefinite hanging
        overall_timeout = (config.timeout_ms / 1000.0 * len(targets)) + 60  # Add 60 seconds buffer
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=overall_timeout
        )
    except asyncio.TimeoutError:
        logger.error(f"Overall screenshot process timed out after {overall_timeout}s")
        # Cancel remaining tasks and return what we have
        for task in tasks:
            if not task.done():
                task.cancel()
        
        # Return targets with timeout errors
        for target in targets:
            if not hasattr(target, 'error') or target.error is None:
                target.error = NavigationError(
                    "Screenshot process timed out",
                    code="OVERALL_TIMEOUT"
                )
        return targets
    
    # Handle any exceptions that occurred
    processed_targets = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Error processing target {targets[i].host}: {result}")
            targets[i].error = NavigationError(
                f"Processing failed: {result}",
                code="PROCESSING_ERROR"
            )
            processed_targets.append(targets[i])
        else:
            processed_targets.append(result)
    
    return processed_targets


async def test_domain_resolution(targets: List[Target], config: AppConfig) -> List[Target]:
    """Test domain resolution and return only targets with a working HTTP response (2xx/3xx/401/403)."""
    semaphore = asyncio.Semaphore(config.concurrency)
    
    async def test_single_target(target: Target) -> Target:
        async with semaphore:
            async with BrowserManager(config) as browser_mgr:
                page = await browser_mgr.create_page()
                try:
                    # Test URL resolution with shorter timeout
                    test_timeout = min(config.timeout_ms, 15000)  # Max 15 seconds for testing
                    final_url, status_code = await try_urls(target.host, page, test_timeout)
                    
                    # Only include targets that resolve to a working HTTP response
                    if (200 <= status_code < 400) or status_code in (401, 403):
                        logger.debug(f"Target {target.host} resolves successfully (HTTP {status_code})")
                        return target
                    else:
                        logger.debug(f"Target {target.host} failed resolution (HTTP {status_code})")
                        target.error = NavigationError(
                            f"Domain did not return a working HTTP response (got {status_code})",
                            code="DOMAIN_RESOLUTION_FAILED"
                        )
                        return target
                        
                except Exception as e:
                    # Handle Playwright errors gracefully without logging asyncio errors
                    error_msg = str(e)
                    if "net::ERR_ABORTED" in error_msg or "frame was detached" in error_msg:
                        logger.debug(f"Target {target.host} connection aborted (normal for unreachable domains)")
                    else:
                        logger.debug(f"Target {target.host} failed resolution test: {e}")
                    
                    target.error = NavigationError(
                        f"Domain resolution test failed: {error_msg}",
                        code="RESOLUTION_TEST_FAILED"
                    )
                    return target
                finally:
                    try:
                        await page.close()
                    except Exception:
                        pass  # Ignore errors when closing page
    
    # Test all targets concurrently with proper exception handling
    logger.info(f"Testing resolution for {len(targets)} targets")
    
    # Use return_exceptions=True to prevent asyncio errors from bubbling up
    results = await asyncio.gather(*[test_single_target(target) for target in targets], return_exceptions=True)
    
    # Handle any exceptions that occurred during testing
    processed_targets = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Unexpected error testing target {targets[i].host}: {result}")
            targets[i].error = NavigationError(
                f"Unexpected error during resolution test: {result}",
                code="UNEXPECTED_ERROR"
            )
            processed_targets.append(targets[i])
        else:
            processed_targets.append(result)
    
    # Filter to only targets that resolved successfully
    resolving_targets = [target for target in processed_targets if not target.error]
    failed_targets = [target for target in processed_targets if target.error]
    
    logger.info(f"Resolution test complete: {len(resolving_targets)} resolved, {len(failed_targets)} failed")
    
    return resolving_targets


if __name__ == "__main__":
    # Test code
    pass
