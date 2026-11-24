import json
from playwright.sync_api import sync_playwright

DRIVER_URL = "https://fantasy.formula1.com/en/statistics/details?tab=driver&filter=fPoints"
CONSTRUCTOR_URL = "https://fantasy.formula1.com/en/statistics/details?tab=constructor&filter=fPoints"

EXTRACT_JS = """
() => {
  // 抓出所有可能是一筆資料列的區塊（tr 或帶有 row/card/item/stat 的 div/li）
  const candidates = Array.from(
    document.querySelectorAll('table tbody tr, [role="row"], [class*="row"], [class*="Row"], [class*="item"], [class*="Item"], li')
  );

  const items = [];
  for (const el of candidates) {
    // 過濾太大的外層容器，避免整張大表被當成一筆
    const txt = (el.innerText || '').trim();
    if (!txt || txt.length > 400) continue;
    if (!txt.includes('$')) continue;

    const tokens = txt.split('\\n').map(s => s.trim()).filter(Boolean);
    const costToken = tokens.find(t => /^\\$?\\d+(\\.\\d+)?\\s*M?$/i.test(t) && t.includes('$'));
    const numTokens = tokens.filter(t => /^-?\\d+(\\.\\d+)?$/.test(t));

    const ignoreWords = /^(game stats|driver|constructor|team|current cost|points per million|value for money|rank|pts|ppm|budget|price)$/i;
    const name = tokens.find(t =>
      !t.includes('$') &&
      !/^-?\\d+(\\.\\d+)?$/.test(t) &&
      !ignoreWords.test(t) &&
      t.length >= 2 &&
      t.length <= 40
    );

    if (name && costToken && numTokens.length > 0) {
      items.push({
        name,
        current_cost: parseFloat(costToken.replace(/[^0-9.]/g, '')),
        points_per_million: parseFloat(numTokens[numTokens.length - 1])
      });
    }
  }

  const dedup = {};
  for (const it of items) {
    if (!isNaN(it.current_cost) && !isNaN(it.points_per_million)) {
      dedup[it.name] = it;
    }
  }
  return Object.values(dedup);
}
"""

def scrape_tab(page, label, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)

    # 嘗試點擊 Value for Money 篩選
    try:
        vfm = page.get_by_text("Value for Money", exact=False)
        if vfm.count() > 0:
            vfm.first.click()
            page.wait_for_timeout(2000)
    except Exception:
        pass

    # 在 log 印出包含 $ 的文字片段，方便判斷實際排版格式
    sample_lines = page.evaluate("""
      () => document.body.innerText
        .split('\\n')
        .map(s => s.trim())
        .filter(s => s.includes('$'))
        .slice(0, 25)
    """)
    print(f"[{label}] Sample '$' lines:", sample_lines)

    return page.evaluate(EXTRACT_JS)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        drivers = scrape_tab(page, "DRIVERS", DRIVER_URL)
        constructors = scrape_tab(page, "CONSTRUCTORS", CONSTRUCTOR_URL)
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
