import json
from playwright.sync_api import sync_playwright

DRIVER_URL = "https://fantasy.formula1.com/en/statistics/details?tab=driver&filter=fPoints"
CONSTRUCTOR_URL = "https://fantasy.formula1.com/en/statistics/details?tab=constructor&filter=fPoints"

EXTRACT_JS = """
() => {
  const candidates = Array.from(
    document.querySelectorAll('table tbody tr, [role="row"], [class*="row"], [class*="Row"], [class*="item"], [class*="Item"], li')
  );

  const ignoreWords = /^(game stats|driver|constructor|team|current cost|points per million|value for money|total fantasy points scored|average fantasy points scored|rank|pts|ppm|budget|price)$/i;

  const items = [];
  for (const el of candidates) {
    const txt = (el.innerText || '').trim();
    if (!txt || txt.length > 400 || !txt.includes('$')) continue;

    // 依換行或連續空白拆出所有文字片段
    const rawTokens = txt
      .split(/\\n+/)
      .flatMap(line => line.split(/\\s{2,}/))
      .map(s => s.trim())
      .filter(Boolean);

    const costToken = rawTokens.find(t => /^\\$?\\d+(\\.\\d+)?\\s*M?$/i.test(t) && t.includes('$'));
    const numTokens = rawTokens.filter(t => /^-?\\d+(\\.\\d+)?$/.test(t));
    if (!costToken || numTokens.length === 0) continue;

    // 過濾出候選姓名片段（排除價格、純數字與介面字眼）
    const nameTokens = rawTokens.filter(t =>
      !t.includes('$') &&
      !/^-?\\d+(\\.\\d+)?$/.test(t) &&
      !ignoreWords.test(t) &&
      t.length >= 2 &&
      t.length <= 35
    );

    let fullName = null;
    if (nameTokens.length >= 2) {
      // 優先檢查是否有連續兩個單字組成「名 + 姓」（例如 "Kimi", "Antonelli" -> "Kimi Antonelli"）
      for (let i = 0; i < nameTokens.length - 1; i++) {
        const a = nameTokens[i];
        const b = nameTokens[i + 1];
        if (!a.includes(' ') && !b.includes(' ') && /^[A-Za-zÀ-ÿ.'-]+$/.test(a) && /^[A-Za-zÀ-ÿ.'-]+$/.test(b)) {
          fullName = `${a} ${b}`;
          break;
        }
      }
      if (!fullName) {
        fullName = nameTokens.find(p => p.includes(' ')) || nameTokens[0];
      }
    } else if (nameTokens.length === 1) {
      fullName = nameTokens[0];
    }

    if (fullName) {
      items.push({
        name: fullName,
        current_cost: parseFloat(costToken.replace(/[^0-9.]/g, '')),
        points_per_million: parseFloat(numTokens[numTokens.length - 1])
      });
    }
  }

  const dedup = {};
  for (const it of items) {
    if (!isNaN(it.current_cost) && !isNaN(it.points_per_million)) {
      // 若同一個名字出現多次，保留較完整的名稱（字數較長者）
      if (!dedup[it.name] || it.name.length > dedup[it.name].name.length) {
        dedup[it.name] = it;
      }
    }
  }
  return Object.values(dedup);
}
"""

def switch_to_vfm(page, label):
    for btn_text in ["Accept All", "Accept", "Agree", "Reject All"]:
        try:
            btn = page.get_by_role("button", name=btn_text, exact=False)
            if btn.count() > 0 and btn.first.is_visible():
                btn.first.click(timeout=3000)
                page.wait_for_timeout(800)
                break
        except Exception:
            pass

    clicked = False
    li_locator = page.locator("li").filter(has_text="Value For Money")
    for i in range(li_locator.count()):
        item = li_locator.nth(i)
        try:
            if item.is_visible():
                item.scroll_into_view_if_needed()
                item.click(timeout=5000)
                clicked = True
                break
        except Exception:
            continue

    if not clicked:
        page.evaluate("""
          () => {
            const lis = Array.from(document.querySelectorAll('li')).filter(
              li => (li.innerText || '').trim().toLowerCase().includes('value for money')
            );
            for (const li of lis) {
              const rect = li.getBoundingClientRect();
              if (rect.width > 0 && rect.height > 0) {
                li.click();
                const span = li.querySelector('span');
                if (span) span.click();
                return true;
              }
            }
            return false;
          }
        """)

    page.wait_for_timeout(3000)

def scrape_tab(page, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    switch_to_vfm(page, url)
    return page.evaluate(EXTRACT_JS)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
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
