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

def debug_vfm_elements(page, label):
    info = page.evaluate("""
      () => {
        const all = Array.from(document.querySelectorAll('*'));
        const matches = all.filter(el => {
          const t = (el.innerText || '').trim();
          return (t === 'Value For Money' || t === 'Total Fantasy Points Scored') && el.children.length <= 2;
        });
        return matches.map(el => {
          const rect = el.getBoundingClientRect();
          const style = window.getComputedStyle(el);
          return {
            text: (el.innerText || '').trim(),
            tag: el.tagName,
            cls: el.className,
            parentTag: el.parentElement ? el.parentElement.tagName : null,
            parentCls: el.parentElement ? el.parentElement.className : null,
            display: style.display,
            visibility: style.visibility,
            w: Math.round(rect.width),
            h: Math.round(rect.height)
          };
        });
      }
    """)
    print(f"[{label}][VFM_DEBUG] {info}")

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

    debug_vfm_elements(page, label)

    # 嘗試直接用 JS 觸發 Value For Money 相關元素的 click / mousedown / pointerdown
    res = page.evaluate("""
      () => {
        const els = Array.from(document.querySelectorAll('*')).filter(el => {
          const t = (el.innerText || '').trim();
          return t === 'Value For Money' && el.children.length <= 2;
        });
        let count = 0;
        for (const el of els) {
          for (const target of [el, el.parentElement, el.parentElement?.parentElement]) {
            if (!target) continue;
            ['pointerdown', 'mousedown', 'mouseup', 'click'].forEach(ev => {
              target.dispatchEvent(new MouseEvent(ev, { bubbles: true, cancelable: true, view: window }));
            });
            if (typeof target.click === 'function') target.click();
            count++;
          }
        }
        return { matched: els.length, dispatched: count };
      }
    """)
    page.wait_for_timeout(2500)
    after_sample = page.evaluate(EXTRACT_JS)[:2]
    print(f"[{label}][JS_DISPATCH={res}][AFTER] {after_sample}")

def scrape_tab(page, label, url):
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(5000)
    switch_to_vfm(page, label)
    return page.evaluate(EXTRACT_JS)

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
