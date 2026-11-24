import json
from playwright.sync_api import sync_playwright

DRIVER_URL = "https://fantasy.formula1.com/en/statistics/details?tab=driver&filter=fPoints"
CONSTRUCTOR_URL = "https://fantasy.formula1.com/en/statistics/details?tab=constructor&filter=fPoints"

EXTRACT_JS = """
() => {
  const candidates = Array.from(
    document.querySelectorAll('table tbody tr, [role="row"], [class*="row"], [class*="Row"], [class*="item"], [class*="Item"], li')
  );

  const items = [];
  for (const el of candidates) {
    const txt = (el.innerText || '').trim();
    if (!txt || txt.length > 400 || !txt.includes('$')) continue;

    const tokens = txt.split('\\n').map(s => s.trim()).filter(Boolean);
    const costToken = tokens.find(t => /^\\$?\\d+(\\.\\d+)?\\s*M?$/i.test(t) && t.includes('$'));
    const numTokens = tokens.filter(t => /^-?\\d+(\\.\\d+)?$/.test(t));

    const ignoreWords = /^(game stats|driver|constructor|team|current cost|points per million|value for money|total fantasy points scored|rank|pts|ppm|budget|price)$/i;
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

def debug_and_switch(page, label):
    # 印出頁面上所有 <select> 選項與包含 Value / Points / Filter 的文字
    debug_info = page.evaluate("""
      () => {
        const selects = Array.from(document.querySelectorAll('select')).map(s => ({
          id: s.id,
          name: s.name,
          options: Array.from(s.options).map(o => ({ value: o.value, text: o.text.trim() }))
        }));
        const matchedTexts = Array.from(document.querySelectorAll('button, a, [role="option"], [role="tab"], label, div, span'))
          .map(el => (el.innerText || '').trim())
          .filter(t => t.length > 0 && t.length < 60 && /value|points|money|filter|ppm/i.test(t));
        return { selects, matchedTexts: [...new Set(matchedTexts)].slice(0, 30) };
      }
    """)
    print(f"[{label}][DEBUG] selects:", debug_info["selects"])
    print(f"[{label}][DEBUG] matchedTexts:", debug_info["matchedTexts"])

    # 若有 <select> 選項包含 value / money / ppm，直接用 select_option 切換
    for s in debug_info["selects"]:
        for opt in s["options"]:
            if "value" in opt["text"].lower() or "money" in opt["text"].lower() or "ppm" in opt["value"].lower():
                try:
                    selector = f"#{s['id']}" if s["id"] else "select"
                    page.select_option(selector, value=opt["value"])
                    page.wait_for_timeout(2000)
                    print(f"[{label}][DEBUG] Selected option:", opt)
                    return
                except Exception as e:
                    print(f"[{label}][DEBUG] select_option error:", e)

def scrape_tab(page, label, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    debug_and_switch(page, label)
    data = page.evaluate(EXTRACT_JS)
    print(f"[{label}] Sample extracted:", data[:3])
    return data

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
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
