import asyncio
import urllib.parse
from pathlib import Path
from datetime import datetime
from playwright.async_api import async_playwright

M3U8_FILE = "TheTVApp.m3u8"
BASE_URL = "https://thetvapp.to"
CHANNEL_LIST_URL = f"{BASE_URL}/tv"

SECTIONS_TO_APPEND = {
    "/nba": "NBA",
    "/mlb": "MLB",
    "/wnba": "WNBA",
    "/nfl": "NFL",
    "/ncaaf": "NCAAF",
    "/ncaab": "NCAAB",
    "/soccer": "Soccer",
    "/ppv": "PPV",
    "/events": "Events"
}

def extract_real_m3u8(url: str):
    if "ping.gif" in url and "mu=" in url:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        mu = qs.get("mu", [None])[0]
        if mu:
            return urllib.parse.unquote(mu)
    if ".m3u8" in url:
        return url
    return None

async def scrape_tv_urls():
    urls = []
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        print(f"🔄 Loading /tv channel list...")
        await page.goto(CHANNEL_LIST_URL)
        links = await page.locator("ol.list-group a").all()
        hrefs = [await link.get_attribute("href") for link in links if await link.get_attribute("href")]
        await page.close()

        for href in hrefs:
            full_url = BASE_URL + href
            print(f"🎯 Scraping TV page: {full_url}")
            for quality in ["SD", "HD"]:
                stream_url = None
                new_page = await context.new_page()

                async def handle_response(response):
                    nonlocal stream_url
                    real = extract_real_m3u8(response.url)
                    if real and not stream_url:
                        stream_url = real

                new_page.on("response", handle_response)
                await new_page.goto(full_url)

                try:
                    await new_page.get_by_text(f"Load {quality} Stream", exact=True).click(timeout=5000)
                except:
                    pass

                await asyncio.sleep(4)
                await new_page.close()

                if stream_url:
                    # Add timestamp to URL to force update on each run
                    stream_url = f"{stream_url}?t={int(datetime.utcnow().timestamp())}"
                    print(f"✅ {quality}: {stream_url}")
                    urls.append(stream_url)
                    break
                else:
                    print(f"❌ {quality} not found")

        await browser.close()
    return urls

async def scrape_section_urls(context, section_path, group_name):
    urls = []
    page = await context.new_page()
    section_url = BASE_URL + section_path
    print(f"\n📁 Loading section: {section_url}")
    await page.goto(section_url)
    links = await page.locator("ol.list-group a").all()
    hrefs_and_titles = []

    for link in links:
        href = await link.get_attribute("href")
        title_raw = await link.text_content()
        if href and title_raw:
            title = " - ".join(line.strip() for line in title_raw.splitlines() if line.strip())
            hrefs_and_titles.append((href, title))

    await page.close()

    for href, title in hrefs_and_titles:
        full_url = BASE_URL + href
        print(f"🎯 Scraping {group_name}: {title}")

        for quality in ["SD", "HD"]:
            stream_url = None
            new_page = await context.new_page()

            async def handle_response(response):
                nonlocal stream_url
                real = extract_real_m3u8(response.url)
                if real and not stream_url:
                    stream_url = real

            new_page.on("response", handle_response)
            await new_page.goto(full_url)

            try:
                await new_page.get_by_text(f"Load {quality} Stream", exact=True).click(timeout=5000)
            except:
                pass

            await asyncio.sleep(4)
            await new_page.close()

            if stream_url:
                # Add timestamp to URL to force update on each run
                stream_url = f"{stream_url}?t={int(datetime.utcnow().timestamp())}"
                print(f"✅ {quality}: {stream_url}")
                urls.append((stream_url, group_name, title))
                break
            else:
                print(f"❌ {quality} not found")

    return urls

async def scrape_all_append_sections():
    all_urls = []
    async with async_playwright() as p:
        browser = await p.firefox.launch(headless=True)
        context = await browser.new_context()

        for section_path, group_name in SECTIONS_TO_APPEND.items():
            urls = await scrape_section_urls(context, section_path, group_name)
            all_urls.extend(urls)

        await browser.close()
    return all_urls

def clean_m3u_header_with_epg(lines):
    lines = [line for line in lines if not line.strip().startswith("#EXTM3U")]
    timestamp = int(datetime.utcnow().timestamp())
    lines.insert(0, f'#EXTM3U url-tvg="https://tinyurl.com/DrewLive002-epg" # Updated: {timestamp}')
    return lines

def replace_urls_in_tv_section(lines, new_urls):
    new_lines = []
    url_idx = 0
    for line in lines:
        if line.strip().startswith("http"):
            if url_idx < len(new_urls):
                new_lines.append(new_urls[url_idx])
                url_idx += 1
            else:
                # Skip old URLs if no new URL to replace with
                continue
        else:
            new_lines.append(line)
    # Append any leftover new URLs if new_urls longer than old URLs count
    if url_idx < len(new_urls):
        new_lines.extend(new_urls[url_idx:])
    return new_lines

def remove_old_section_entries(lines, section_groups):
    cleaned = []
    skip_next = False
    for line in lines:
        if skip_next:
            skip_next = False
            continue
        if line.startswith("#EXTINF") and any(f'group-title="{group}"' in line for group in section_groups):
            skip_next = True
            continue
        cleaned.append(line)
    return cleaned

def append_new_streams(lines, new_urls_with_groups):
    lines = [line for line in lines if not line.strip().startswith("#EXTM3U")]

    for url, group, title in new_urls_with_groups:
        if group == "MLB":
            lines.append(f'#EXTINF:-1 tvg-id="MLB.Baseball.Dummy.us" tvg-name="{title}" tvg-logo="http://drewlive24.duckdns.org:9000/Logos/Baseball-2.png" group-title="MLB",{title}')
        elif group == "PPV":
            lines.append(f'#EXTINF:-1 tvg-id="PPV.EVENTS.Dummy.us" tvg-name="{title}" tvg-logo="http://drewlive24.duckdns.org:9000/Logos/PPV.png" group-title="PPV",{title}')
        else:
            lines.append(f'#EXTINF:-1 group-title="{group}",{title}')
        lines.append(url)

    lines = [line for line in lines if line.strip()]
    lines.insert(0, '#EXTM3U url-tvg="https://tinyurl.com/DrewLive002-epg"')
    return lines

async def main():
    if not Path(M3U8_FILE).exists():
        print(f"❌ File not found: {M3U8_FILE}")
        return

    with open(M3U8_FILE, "r", encoding="utf-8") as f:
        lines = f.read().splitlines()

    # Clean old header, add new header with fresh timestamp
    lines = clean_m3u_header_with_epg(lines)

    print("🔧 Replacing /tv stream URLs...")
    tv_new_urls = await scrape_tv_urls()
    if not tv_new_urls:
        print("❌ No TV URLs scraped.")
        return

    updated_lines = replace_urls_in_tv_section(lines, tv_new_urls)

    print("\n📦 Scraping all other sections (NBA, NFL, Events, etc)...")
    append_new_urls = await scrape_all_append_sections()

    # Remove old sections before appending fresh
    section_groups = list(SECTIONS_TO_APPEND.values())
    updated_lines = remove_old_section_entries(updated_lines, section_groups)

    if append_new_urls:
        updated_lines = append_new_streams(updated_lines, append_new_urls)

    # Final header refresh with timestamp before writing
    updated_lines = clean_m3u_header_with_epg(updated_lines)

    with open(M3U8_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(updated_lines))

    print(f"\n✅ {M3U8_FILE} updated: header and URLs fully refreshed.")

if __name__ == "__main__":
    asyncio.run(main())
