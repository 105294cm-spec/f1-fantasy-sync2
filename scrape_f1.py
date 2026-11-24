import json
from playwright.sync_api import sync_playwright

DRIVER_URL = "https://fantasy.formula1.com/en/statistics/details?tab=driver&filter=fPoints"
CONSTRUCTOR_URL = "https://fantasy.formula1.com/en/statistics/details?tab=constructor&filter=fPoints"

EXTRACT_JS = """
() => {
  // 優先抓真正的表格列 tr
  const rows = Array.from(document.querySelectorAll('table tbody tr'));
  const items = [];

  for (const row of rows) {
    const tokens = row.innerText
      .split('\\n')
      .map(s => s.trim())
      .filter(Boolean);

    // 車手/車隊價格通常長這樣: $27.7M 或 27.7M
    const costStr = tokens.find(t => /^\\$?\\d+(\\.\\d+)?M$/i.test(t));
    if (!costStr) continue;

    // 找出所有數字 token
    const numTokens = tokens.filter(t => /^-?\\d+(\\.\\d+)?$/.test(t));
    if (numTokens.length === 0) continue;

    // 找出候選名稱（排除純數字、價格、常見介面字眼）
    const ignoreWords = /^(game stats|driver|constructor|team|current cost|points per million|value for money|rank|pts|ppm)$/i;
    const name = tokens.find(t =>
      !/^\\$?\\d/.test(t) &&
      !/^-?\\d/.test(t) &&
      !ignoreWords.test(t) &&
      t.length >= 2
    );

    if (name) {
      items.push({
        name,
        current_cost: parseFloat(costStr.replace(/[$,a-zA-Z]/g, '')),
        points_per_million: parseFloat(numTokens[numTokens.length - 1])
      });
    }
  }

  const dedup = {};
  for (const it of items) dedup[it.name] = it;
  return Object.values(dedup);
}
"""

def scrape_tab(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    # 等待表格列出現（最多等 20 秒）
    try:
        page.wait_for_selector("table tbody tr", timeout=20000)
    except Exception:
        pass
    page.wait_for_timeout(2000)

    try:
        vfm = page.get_by_text("Value for Money", exact=False)
        if vfm.count() > 0:
            vfm.first.click()
            page.wait_for_timeout(1500)
    except Exception:
        pass

    return page.evaluate(EXTRACT_JS)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        drivers = scrape_tab(page, DRIVER_URL)
        constructors = scrape_tab(page, CONSTRUCTOR_URL)
        browser.close()

    output = {
        "constructors": constructors,
        "drivers": drivers
    }
    with open("f1_fantasy_data.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(constructors)} constructors and {len(drivers)} drivers.")

if __name__ == "__main__":
    main()
