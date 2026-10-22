"""Check real dashboard/full-map marker alignment without modifying any records."""
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
from sqlalchemy import create_engine, text
from playwright.async_api import async_playwright, expect
from app.core.config import settings
from app.core.security import create_access_token


async def main():
    engine = create_engine(settings.SYNC_DATABASE_URL)
    try:
        with engine.connect() as connection:
            user_id = connection.execute(text("SELECT id FROM users WHERE is_active=true LIMIT 1")).scalar_one()
            before = connection.execute(text("SELECT id, name, latitude, longitude FROM cameras ORDER BY name")).mappings().all()
        expected = next(row for row in before if row["name"] == "General Entrance")
        token = create_access_token(str(user_id), timedelta(minutes=30))
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="msedge", headless=True)
            context = await browser.new_context(viewport={"width":1440, "height":1000})
            await context.add_cookies([{"name":"cs_token", "value":token, "url":"http://localhost:3000"}])
            await context.add_init_script(f"""
              if (location.origin === 'http://localhost:3000') localStorage.setItem('access_token', {json.dumps(token)});
              window.__geolocationCalls = 0;
              navigator.geolocation.getCurrentPosition = () => {{ window.__geolocationCalls++; }};
              navigator.geolocation.watchPosition = () => {{ window.__geolocationCalls++; return 0; }};
            """)
            page = await context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            try:
                response = await context.request.get("http://localhost:8000/api/v1/cameras/", headers={"Authorization":f"Bearer {token}"})
                assert response.ok
                cameras = await response.json()
                print("Actual camera status:", ", ".join(f"{cam['name']}={cam['status']}" for cam in cameras), flush=True)
                for path, camera_size in (("/dashboard",12), ("/map",28)):
                    await page.goto(f"http://localhost:3000{path}", wait_until="domcontentloaded")
                    if path == "/dashboard":
                        await page.get_by_text("Live Cameras", exact=True).scroll_into_view_if_needed()
                    campus = page.locator(".campus-marker")
                    await expect(campus).to_have_count(1, timeout=15000)
                    await expect(page.locator('.leaflet-marker-icon[title="General Entrance"]')).to_have_count(1, timeout=15000)
                    await expect(page.locator('.leaflet-marker-icon[title="Classroom"]')).to_have_count(1, timeout=15000)
                    await expect(page.locator(".leaflet-tile-loaded").first).to_be_visible(timeout=20000)
                    assert await page.locator('.leaflet-overlay-pane path[stroke="#2563eb"]').count() == 0
                    assert await page.evaluate("window.__geolocationCalls") == 0

                    geometry = f"""() => {{
                      const map=document.querySelector('.leaflet-container').getBoundingClientRect();
                      const campus=document.querySelector('.campus-marker').getBoundingClientRect();
                      const entrance=document.querySelector('.leaflet-marker-icon[title="General Entrance"]').getBoundingClientRect();
                      return {{campus:[campus.left+14,campus.top+40], entrance:[entrance.left+{camera_size}/2,entrance.top+{camera_size}/2], center:[map.left+map.width/2,map.top+map.height/2], pane:document.querySelector('.leaflet-map-pane').style.transform}};
                    }}"""
                    initial = await page.evaluate(geometry)
                    for index in (0,1):
                        assert abs(initial["campus"][index] - initial["entrance"][index]) <= 1, initial
                        assert abs(initial["campus"][index] - initial["center"][index]) <= 1, initial
                    assert await page.locator('.leaflet-tile-loaded[src*="/18/"]').count() > 0
                    await page.wait_for_timeout(11000)  # includes a real camera refresh cycle
                    later = await page.evaluate(geometry)
                    assert later == initial, (initial,later)
                    await campus.click()
                    await expect(page.locator(".leaflet-popup-content")).to_have_text("Sreyas Institute of Engineering and Technology")
                    await page.locator(".leaflet-popup-close-button").click()
                    if path == "/map":
                        await page.get_by_role("button",name="Cameras",exact=True).click()
                        assert await page.locator('.leaflet-marker-icon[title="General Entrance"]').count() == 0
                        await expect(campus).to_have_count(1)
                        await page.get_by_role("button",name="Cameras",exact=True).click()
                        await expect(page.locator('.leaflet-marker-icon[title="General Entrance"]')).to_have_count(1)
                        await page.get_by_role("button",name="Incidents",exact=True).click()
                        await expect(campus).to_have_count(1)
                    await page.screenshot(path=str(ROOT / "logs" / f"campus-map-{path.strip('/')}-verified.png"))
                    print(f"{path}: campus and entrance share the map center, zoom 18, labeled campus icon, both camera markers, no blue dot/geolocation/map jump", flush=True)
                assert not errors, errors
            finally:
                await browser.close()
        with engine.connect() as connection:
            after = connection.execute(text("SELECT id, name, latitude, longitude FROM cameras ORDER BY name")).mappings().all()
        assert after == before, "Camera records or coordinates changed"
        print(f"Canonical location matches existing entrance record: {expected['latitude']}, {expected['longitude']}; camera coordinates unchanged", flush=True)
    finally:
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
