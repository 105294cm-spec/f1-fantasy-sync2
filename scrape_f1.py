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

    const ignoreWords = /^(game stats|driver|constructor|team|current cost|points per million|value for money|total fantasy points scored|average fantasy points scored|rank|pts|ppm|budget|price)$/i;
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

def switch_to_vfm(page, label):
    # 1. 若有 Cookie 彈窗先關閉
    for btn_text in ["Accept All", "Accept", "Agree", "Reject All"]:
        try:
            btn = page.get_by_role("button", name=btn_text, exact=False)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click()
                page.wait_for_timeout(800)
                break
        except Exception:
            pass

    # 2. 先點一下目前預設顯示的 "Total Fantasy Points Scored"（若它是折疊選單就會展開）
    try:
        triggers = page.get_by_text("Total Fantasy Points Scored", exact=True)
        for i in range(triggers.count()):
            if triggers.nth(i).is_visible():
                triggers.nth(i).click(force=True)
                page.wait_for_timeout(1000)
                break
    except Exception:
        pass

    # 3. 遍歷所有 "Value For Money" 節點，點擊真正可見的那一個
    clicked = False
    vfm_nodes = page.get_by_text("Value For Money", exact=True)
    count = vfm_nodes.count()
    print(f"[{label}] Found {count} 'Value For Money' nodes")

    for i in range(count):
        node = vfm_nodes.nth(i)
        try:
            if node.is_visible():
                node.scroll_into_view_if_needed()
                node.click(force=True)
                clicked = True
                print(f"[{label}] Clicked visible node index {i}")
                page.wait_for_timeout(2500)
                break
        except Exception as e:
            print(f"[{label}] Node {i} click failed:", e)

    # 若剛剛仍未點到可見節點，直接用 JS 觸發最內層包含 Value For Money 的元素點擊
    if not clicked:
        js_clicked = page.evaluate("""
          () => {
            const els = Array.from(document.querySelectorAll('*'))
              .filter(el => el.children.length === 0 && (el.innerText || '').trim().toLowerCase() === 'value for money');
            for (const el of els) {
              el.click();
              if (el.parentElement) el.parentElement.click();
            }
            return els.length;
          }
        """)
        print(f"[{label}] Fallback JS clicked {js_clicked} leaf nodes")
        page.wait_for_timeout(2500)

    # 4. 確認欄位是否已切換為 Points Per Million
    has_ppm = page.evaluate("() => /points per million/i.test(document.body.innerText)")
    print(f"[{label}] Page now shows 'Points Per Million': {has_ppm}")

def scrape_tab(page, label, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    switch_to_vfm(page, label)
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
