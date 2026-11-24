import json
from playwright.sync_api import sync_playwright

DRIVER_URL = "https://fantasy.formula1.com/en/statistics/details?tab=driver&filter=fPoints"
CONSTRUCTOR_URL = "https://fantasy.formula1.com/en/statistics/details?tab=constructor&filter=fPoints"

EXTRACT_JS = """
() => {
  const rows = Array.from(document.querySelectorAll('table tbody tr, [class*="row"], [class*="Row"]'));
  const items = [];
  for (const row of rows) {
    const tokens = row.innerText.split('\\n').map(s => s.trim()).filter(Boolean);
    const costStr = tokens.find(t => /^\\$?\\d+(\\.\\d+)?M$/i.test(t));
    const nums = tokens.filter(t => /^-?\\d+(\\.\\d+)?$/.test(t));
    const name = tokens.find(t => !/^\\$?\\d/.test(t) && !/^-?\\d/.test(t) && t.length > 2);
    if (name && costStr && nums.length > 0) {
      items.push({
        name,
        current_cost: parseFloat(costStr.replace(/[$,a-zA-Z]/g, '')),
        points_per_million: parseFloat(nums[nums.length - 1])
      });
    }
  }
  const dedup = {};
  for (const it of items) dedup[it.name] = it;
  return Object.values(dedup);
}
"""

def scrape_tab(page, url):
    page.goto(url, wait_until="networkidle", timeout=60000)
    page.wait_for_timeout(3000)
    # 嘗試點擊 Value for Money 篩選（若頁面尚未停在該選項）
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
        page = browser.new_page()
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
