"""Production browser checks using installed Edge and existing cameras/account.

No incident, camera, or user records are inserted or removed. Run with the
backend venv after building/starting the frontend. --expect-regression checks
the original expired-token redirect loop before rebuilding the fixed frontend.
"""
import argparse
import asyncio
import json
import os
import sys
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT / "backend")
sys.path.insert(0, str(ROOT / "backend"))
os.environ.pop("DEBUG", None)

from playwright.async_api import async_playwright, expect
from sqlalchemy import create_engine, text
from app.core.config import settings
from app.core.security import create_access_token


async def main(regression=False):
    engine = create_engine(settings.SYNC_DATABASE_URL)
    try:
        with engine.connect() as connection:
            user_id = connection.execute(text("SELECT id FROM users WHERE is_active=true LIMIT 1")).scalar_one()
    finally:
        engine.dispose()
    token = create_access_token(str(user_id), timedelta(minutes=-1 if regression else 30))
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge", headless=True)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000})
        await context.add_cookies([{"name": "cs_token", "value": token, "url": "http://localhost:3000"}])
        await context.add_init_script(f"""
          if (location.origin === 'http://localhost:3000' && !sessionStorage.getItem('test-initialized')) {{
            localStorage.setItem('access_token', {json.dumps(token)});
            sessionStorage.setItem('test-initialized', 'true');
          }}
          window.__testSockets = [];
          const NativeWebSocket = window.WebSocket;
          window.WebSocket = class extends NativeWebSocket {{
            constructor(...args) {{ super(...args); window.__testSockets.push(this); }}
          }};
        """)
        page = await context.new_page()
        navigations = []
        errors = []
        page.on("framenavigated", lambda frame: navigations.append(frame.url.split("?")[0]) if frame == page.main_frame else None)
        page.on("pageerror", lambda error: errors.append(str(error)))
        try:
            await page.goto("http://localhost:3000/dashboard", wait_until="domcontentloaded")
            if regression:
                await page.wait_for_timeout(8000)
                assert len(navigations) >= 3, f"Expected original redirect loop, got {navigations}"
                print(f"Original regression reproduced: {len(navigations)} navigations in 8 seconds with an expired token")
                return

            await expect(page.get_by_text("2/2 online", exact=True)).to_be_visible(timeout=30000)
            await expect(page.locator("header").get_by_text("Live", exact=True)).to_be_visible(timeout=15000)
            await page.wait_for_function("""() => ['General Entrance', 'Classroom'].every(name => {
              const image = document.querySelector('img[alt="' + name + '"]');
              return image && image.src.startsWith('data:image/jpeg') && image.naturalWidth > 0;
            })""", timeout=30000)
            assert "Loading" not in await page.locator("header").inner_text()
            baseline = len(navigations)
            print("Browser: Live, 2/2 online, both real camera frames, and loaded CSI")
            await page.get_by_text("Live Cameras", exact=True).scroll_into_view_if_needed()
            await page.screenshot(path=str(ROOT / "logs" / "dashboard-regression-verified.png"))

            async def unavailable(route):
                await route.fulfill(status=503, content_type="application/json", body='{"detail":"Temporary test outage"}')

            await page.route("**/api/v1/csi/campus", unavailable)
            await expect(page.get_by_text("Updates unavailable; showing last valid score", exact=True)).to_be_visible(timeout=15000)
            await expect(page.get_by_text("2/2 online", exact=True)).to_be_visible()
            await expect(page.locator("header").get_by_text("Live", exact=True)).to_be_visible()
            assert len(navigations) == baseline
            await page.unroute("**/api/v1/csi/campus", unavailable)
            await expect(page.get_by_text("Updates unavailable; showing last valid score", exact=True)).not_to_be_visible(timeout=15000)
            print("Browser: temporary CSI failure preserves cameras, connection, score, and mounted page")

            await page.route("**/api/v1/cameras/", unavailable)
            await expect(page.get_by_text("Camera updates unavailable; retaining last loaded cameras", exact=True)).to_be_visible(timeout=20000)
            await expect(page.get_by_text("2/2 online", exact=True)).to_be_visible()
            assert len(navigations) == baseline
            await page.unroute("**/api/v1/cameras/", unavailable)
            await expect(page.get_by_text("Camera updates unavailable; retaining last loaded cameras", exact=True)).not_to_be_visible(timeout=20000)
            print("Browser: temporary camera-list failure retains both configured cameras")

            await page.evaluate("""() => window.__testSockets.filter(ws => ws.url.includes('/ws/events') && ws.readyState === 1).forEach(ws => ws.close())""")
            await expect(page.get_by_text("Disconnected", exact=True)).to_be_visible(timeout=2000)
            await expect(page.get_by_text("2/2 online", exact=True)).to_be_visible()
            await expect(page.locator("header").get_by_text("Live", exact=True)).to_be_visible(timeout=10000)
            counts = await page.evaluate("""() => ({
              events: window.__testSockets.filter(ws => ws.url.includes('/ws/events') && ws.readyState < 2).length,
              cameras: window.__testSockets.filter(ws => ws.url.includes('/ws/camera/') && ws.readyState < 2).length
            })""")
            assert counts == {"events": 1, "cameras": 2}, counts
            assert len(navigations) == baseline
            print("Browser: event socket disconnect/reconnect retains camera list; one events socket and two camera sockets")

            # An actual backend 401 must clear both credentials and stay mounted.
            invalid = token.rsplit(".", 1)[0] + ".invalid-signature"
            await page.evaluate("token => { localStorage.setItem('access_token', token); document.cookie = 'cs_token=' + token + '; path=/; SameSite=Strict'; }", invalid)
            await expect(page.get_by_text("Session expired. Sign in", exact=True)).to_be_visible(timeout=15000)
            assert await page.evaluate("localStorage.getItem('access_token')") is None
            assert not any(cookie["name"] == "cs_token" for cookie in await context.cookies())
            assert len(navigations) == baseline
            await page.get_by_text("Session expired. Sign in", exact=True).click()
            await expect(page).to_have_url("http://localhost:3000/login", timeout=10000)
            await page.wait_for_timeout(2000)
            assert page.url == "http://localhost:3000/login"
            assert not errors, errors
            print("Browser: backend 401 clears storage and cookie, stops sockets, and reaches stable login without a reload loop")
            expired = create_access_token(str(user_id), timedelta(minutes=-1))
            await context.add_cookies([{"name":"cs_token", "value":expired, "url":"http://localhost:3000"}])
            await page.goto("http://localhost:3000/login", wait_until="domcontentloaded")
            assert page.url == "http://localhost:3000/login"
            assert not any(cookie["name"] == "cs_token" for cookie in await context.cookies())
            print("Browser: middleware clears an expired cookie and keeps login stable")
        finally:
            await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-regression", action="store_true")
    asyncio.run(main(parser.parse_args().expect_regression))
