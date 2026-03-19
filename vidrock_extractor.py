import nodriver as uc
import asyncio
import re
import logging
import sys
from playwright.async_api import async_playwright

# Setup clean logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("VidRockExtractor")

def normalize_nodriver(obj):
    if isinstance(obj, dict):
        if 'type' in obj and 'value' in obj:
            return normalize_nodriver(obj['value'])
        return {k: normalize_nodriver(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_nodriver(i) for i in obj]
    return obj

async def get_cloudnestra_link(vidrock_url):
    logger.info(f"[*] STEP 1: Getting Cloudnestra link from: {vidrock_url}")
    browser = await uc.start(headless=True)
    page = await browser.get(vidrock_url)
    await asyncio.sleep(15)
    
    # STEP 2: Find vidsrc.net iframe
    logger.info("[*] STEP 2: Searching for VidSrc.net iframe...")
    
    # Use regex on content
    content = normalize_nodriver(await page.get_content())
    vidsrc_match = re.search(r'https?://(?:vidsrc\.net|vsembed\.ru)/embed/(?:movie|tv)/[^"\']+', content)
    vidsrc_src = vidsrc_match.group(0) if vidsrc_match else None
    
    if not vidsrc_src:
        # Fallback to DOM
        vidsrc_src = await page.evaluate("""
            () => {
                const iframes = Array.from(document.querySelectorAll('iframe'));
                const target = iframes.find(f => f.src && (f.src.includes('vidsrc.net') || f.src.includes('vsembed.ru')));
                return target ? target.src : null;
            }
        """)
        vidsrc_src = normalize_nodriver(vidsrc_src)
    
    if not vidsrc_src:
        browser.stop()
        return None
        
    logger.info(f"[✔] Found VidSrc: {vidsrc_src}")
    page = await browser.get(vidsrc_src)
    await asyncio.sleep(10)
    
    # STEP 4: Find Cloudnestra iframe
    logger.info("[*] STEP 4: Searching for Cloudnestra embed...")
    
    # Use regex on content
    content = normalize_nodriver(await page.get_content())
    cloud_match = re.search(r'https?://cloudnestra\.com/rcp/[^"\']+', content)
    cloudnestra_src = cloud_match.group(0) if cloud_match else None
    
    if not cloudnestra_src:
        # Fallback to DOM
        cloudnestra_src = await page.evaluate("""
            () => {
                const iframe = document.getElementById('player_iframe') || document.querySelector('iframe[src*="cloudnestra.com/rcp/"]');
                return iframe ? iframe.src : null;
            }
        """)
        cloudnestra_src = normalize_nodriver(cloudnestra_src)
    
    if not cloudnestra_src:
        # Regex fallback
        content = normalize_nodriver(await page.get_content())
        match = re.search(r'<iframe[^>]+src=["\']([^"\']*cloudnestra\.com/rcp/[^"\']+)["\']', content)
        if match: cloudnestra_src = match.group(1)

    browser.stop()
    
    if cloudnestra_src and cloudnestra_src.startswith("//"):
        cloudnestra_src = "https:" + cloudnestra_src
        
    return cloudnestra_src, vidsrc_src

async def extract_final_stream(cloudnestra_url, referer):
    logger.info(f"[*] STEP 2: Extracting stream from Cloudnestra: {cloudnestra_url}")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            extra_http_headers={"referer": referer}
        )
        page = await context.new_page()
        
        final_link = None
        async def handle_response(response):
            nonlocal final_link
            u = response.url.lower()
            if any(x in u for x in [".m3u8", ".mp4", "playlist.m3u8"]):
                if not any(x in u for x in ["analytics", "beacon", "log", "histats"]):
                    final_link = response.url

        page.on("response", handle_response)
        await context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        await page.goto(cloudnestra_url, wait_until="networkidle")
        
        # Click play button
        play_btn = await page.query_selector("#pl_but, #pl_but_background")
        if play_btn:
            await play_btn.click()
            await asyncio.sleep(5)
            
        if not final_link:
            await page.mouse.click(640, 360)
            await asyncio.sleep(5)
            
        await browser.close()
        return final_link

async def run_precise_extractor(url):
    res = await get_cloudnestra_link(url)
    if not res:
        logger.error("[!] Failed to find Cloudnestra link.")
        return None
        
    cloud_link, vidsrc_link = res
    logger.info(f"[✔] Found Cloudnestra: {cloud_link}")
    return await extract_final_stream(cloud_link, vidsrc_link)

if __name__ == "__main__":
    print("\n" + "="*50)
    print(" HYBRID VIDROCK EXTRACTOR (NODRIVER + PLAYWRIGHT)")
    print("="*50)
    
    try:
        user_url = input("Paste the VidRock URL: ").strip()
        if not user_url:
            user_url = "https://vidrock.ru/mega/tv/62113/1/1"
            
        stream_link = asyncio.run(run_precise_extractor(user_url))
        
        print("\n" + "="*50)
        if stream_link:
            print("FINAL STREAM LINK:")
            print(stream_link)
        else:
            print("FAILED TO EXTRACT STREAM LINK")
        print("="*50)
        
    except (EOFError, KeyboardInterrupt):
        pass
