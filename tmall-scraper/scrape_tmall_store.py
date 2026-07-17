# -*- coding: utf-8 -*-
"""
天猫店铺商品数据采集工具（低风险 / 防封号设计）

采集字段：品名、售价、产品链接、销量、评论数
默认目标：天猫罗技官方旗舰店 https://logitech.tmall.com

防封号策略：
  1. 使用真实浏览器（Playwright 持久化用户目录），你扫码登录一次即可复用；
  2. 单线程 + 每次翻页/进详情页之间随机等待（默认 4~9 秒），模拟真人节奏；
  3. 页面内模拟滚动浏览，不直接刷接口、不带并发；
  4. 检测到滑块/验证码时立刻暂停，等你手动完成后回车继续；
  5. 断点续采：已采集的商品自动跳过，可以分多次、隔天慢慢采完。

用法（本地电脑，需要图形界面）：
  pip install -r requirements.txt
  playwright install chromium
  python scrape_tmall_store.py                # 完整采集并导出 Excel
  python scrape_tmall_store.py --export-only  # 只用已有数据重新导出 Excel
"""

import argparse
import json
import random
import re
import sys
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
PROFILE_DIR = BASE_DIR / "browser-profile"
URLS_FILE = DATA_DIR / "item_urls.json"
ITEMS_FILE = DATA_DIR / "items.jsonl"

# 标题中出现这些词的商品视为“套包/套装”，会被移到 Excel 的第二个工作表，不计入单品
DEFAULT_EXCLUDE_KEYWORDS = ["套装", "套餐", "组合", "礼盒", "礼包", "套包", "两件装", "二件装", "件套"]

UA_HINT = None  # 使用 Playwright 自带 Chrome UA，避免 UA 与浏览器指纹不一致


# ---------------------------------------------------------------- 工具函数

def human_pause(min_s: float, max_s: float, why: str = ""):
    t = random.uniform(min_s, max_s)
    if why:
        print(f"    …等待 {t:.1f}s（{why}）")
    time.sleep(t)


def parse_cn_number(text: str):
    """把 '2.5万+'、'1000+'、'3万' 之类的销量文本转成数字（取下限）。"""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return int(text)
    s = str(text).strip().replace(",", "").replace("+", "")
    m = re.search(r"([\d.]+)\s*万", s)
    if m:
        return int(float(m.group(1)) * 10000)
    m = re.search(r"[\d.]+", s)
    return int(float(m.group(0))) if m else None


def find_first_key(obj, keys):
    """在嵌套 dict/list 中递归查找第一个命中的 key（广度优先，尽量取顶层的值）。"""
    queue = [obj]
    while queue:
        cur = queue.pop(0)
        if isinstance(cur, dict):
            for k in keys:
                if k in cur and cur[k] not in (None, "", []):
                    return cur[k]
            queue.extend(cur.values())
        elif isinstance(cur, list):
            queue.extend(cur)
    return None


def extract_jsonp(body: str):
    """mtop 接口常用 jsonp 包裹：mtopjsonpxx({...})，剥出 JSON。"""
    body = body.strip()
    if body.startswith("{"):
        return json.loads(body)
    m = re.search(r"^[\w$.]+\((.*)\)\s*;?\s*$", body, re.S)
    if m:
        return json.loads(m.group(1))
    raise ValueError("not json/jsonp")


def item_id_from_url(url: str):
    q = parse_qs(urlparse(url).query)
    if "id" in q:
        return q["id"][0]
    m = re.search(r"[?&]id=(\d+)", url)
    return m.group(1) if m else None


# ---------------------------------------------------------------- 反爬检测

CAPTCHA_MARKERS = ["punish", "captcha", "_____tmd_____", "x5secdata"]


def wait_if_captcha(page) -> bool:
    """检测滑块/验证码页面；命中则暂停等待人工处理。返回是否遇到过验证。"""
    hit = any(m in page.url for m in CAPTCHA_MARKERS)
    if not hit:
        try:
            hit = page.locator("#nc_1_wrapper, .nc-container, #nocaptcha").count() > 0
        except Exception:
            hit = False
    if hit:
        print("\n" + "!" * 60)
        print("!! 检测到滑块/安全验证。请在浏览器窗口中手动完成验证，")
        print("!! 完成后回到这里按回车继续。建议之后适当加大 --min-delay。")
        print("!" * 60)
        input(">> 验证完成后按回车继续 ")
        time.sleep(2)
        return True
    return False


def kicked_to_login(page) -> bool:
    """被风控踢回登录页时，暂停等待人工重新扫码。返回是否发生过。"""
    if "login.tmall.com" in page.url or "login.taobao.com" in page.url:
        print("\n" + "!" * 60)
        print("!! 天猫要求重新登录（风控信号）。请在浏览器窗口重新扫码登录。")
        print("!! 如果今天已经被踢下线 3 次以上，强烈建议直接关闭程序，")
        print("!! 明天再继续（进度不会丢）。反复硬登会让风控越来越严。")
        print("!" * 60)
        input(">> 重新登录完成后按回车继续，或按 Ctrl+C 退出 ")
        time.sleep(2)
        return True
    return False


def ensure_logged_in(page, shop_url: str):
    page.goto(shop_url, wait_until="domcontentloaded", timeout=60000)
    wait_if_captcha(page)
    for _ in range(2):
        if "login.tmall.com" in page.url or "login.taobao.com" in page.url:
            print("\n>> 需要登录：请在打开的浏览器窗口里用手机淘宝/天猫 App 扫码登录。")
            print(">> 登录状态会保存在 browser-profile/ 目录，下次运行无需再登录。")
            input(">> 登录完成、看到店铺页面后按回车继续 ")
            page.goto(shop_url, wait_until="domcontentloaded", timeout=60000)
            wait_if_captcha(page)
        else:
            break
    print(f">> 当前页面：{page.url}")


# ---------------------------------------------------------------- 第一阶段：收集商品链接

def scroll_page(page, rounds=6):
    for _ in range(rounds):
        page.mouse.wheel(0, random.randint(600, 1200))
        time.sleep(random.uniform(0.5, 1.2))


def collect_item_urls_on_page(page) -> set:
    urls = set()
    anchors = page.eval_on_selector_all(
        "a[href*='detail.tmall.com/item'], a[href*='item.taobao.com/item'], a[href*='chaoshi.detail.tmall.com/item']",
        "els => els.map(e => e.href)",
    )
    for u in anchors:
        iid = item_id_from_url(u)
        if iid:
            urls.add(f"https://detail.tmall.com/item.htm?id={iid}")
    return urls


def click_next_page(page) -> bool:
    """尝试点击“下一页”按钮，成功返回 True。兼容新旧店铺装修的多种写法。"""
    candidates = [
        "a.J_SearchAsync.next",           # 旧版店铺 search.htm
        "a[class*='next']:not([class*='disable'])",
        "button[class*='next']:not([disabled])",
        "li[title='下一页'] a",
        "text=下一页",
    ]
    for sel in candidates:
        try:
            loc = page.locator(sel).first
            if loc.count() > 0 and loc.is_visible():
                cls = (loc.get_attribute("class") or "")
                if "disable" in cls or "disabled" in cls:
                    return False
                loc.click(timeout=5000)
                page.wait_for_load_state("domcontentloaded", timeout=30000)
                return True
        except Exception:
            continue
    return False


def stage1_collect_urls(page, shop_url, max_pages, dmin, dmax) -> list:
    known = set()
    if URLS_FILE.exists():
        known = set(json.loads(URLS_FILE.read_text("utf-8")))
        print(f">> 已有 {len(known)} 条商品链接（断点续采），本次将增量补充。")

    # 优先走传统的 search.htm 全部宝贝分页；走不通时退回当前页面点“下一页”
    origin = f"https://{urlparse(shop_url).netloc}"
    list_entries = [f"{origin}/search.htm", f"{origin}/category.htm", shop_url]

    entry_ok = None
    for entry in list_entries:
        try:
            page.goto(entry, wait_until="domcontentloaded", timeout=60000)
            wait_if_captcha(page)
            scroll_page(page)
            found = collect_item_urls_on_page(page)
            print(f">> 入口 {entry} ：本页发现 {len(found)} 个商品链接")
            if found:
                entry_ok = entry
                known |= found
                break
        except PWTimeout:
            continue
    if not entry_ok:
        print("!! 没能在店铺页面上找到商品链接，请把浏览器窗口里的实际情况反馈给我。")
        return sorted(known)

    stale_rounds = 0
    for page_no in range(2, max_pages + 1):
        human_pause(dmin, dmax, f"准备第 {page_no} 页")
        moved = False
        if "search.htm" in entry_ok:
            try:
                page.goto(f"{entry_ok}?pageNo={page_no}", wait_until="domcontentloaded", timeout=60000)
                moved = True
            except PWTimeout:
                moved = False
        if not moved:
            moved = click_next_page(page)
        if not moved:
            print(">> 没有下一页了，链接收集结束。")
            break
        wait_if_captcha(page)
        scroll_page(page)
        found = collect_item_urls_on_page(page)
        new = found - known
        known |= found
        print(f">> 第 {page_no} 页：{len(found)} 个链接，其中新增 {len(new)} 个（累计 {len(known)}）")
        stale_rounds = stale_rounds + 1 if not new else 0
        if stale_rounds >= 2:
            print(">> 连续两页没有新商品，认为已到最后一页。")
            break
        URLS_FILE.write_text(json.dumps(sorted(known), ensure_ascii=False, indent=1), "utf-8")

    URLS_FILE.write_text(json.dumps(sorted(known), ensure_ascii=False, indent=1), "utf-8")
    print(f">> 商品链接收集完成：共 {len(known)} 个，已保存到 {URLS_FILE}")
    return sorted(known)


# ---------------------------------------------------------------- 第二阶段：逐个采集详情

def extract_from_detail(page, captured: dict) -> dict:
    """优先从 mtop 详情接口 JSON 提取，DOM 文本兜底。"""
    row = {"title": None, "price": None, "sales": None, "comments": None}

    data = captured.get("detail_json")
    if data:
        row["title"] = find_first_key(data, ["title", "itemTitle"])
        price = find_first_key(data, ["priceText", "price", "promotionPrice", "priceMoney"])
        if isinstance(price, dict):
            price = find_first_key(price, ["priceText", "price", "text"])
        row["price"] = price
        row["sales"] = find_first_key(data, ["sellCount", "soldQuantity", "vagueSellCount", "soldCount"])
        row["comments"] = find_first_key(data, ["commentCount", "rateCount", "totalCount"])

    def dom_text(patterns):
        try:
            body = page.inner_text("body", timeout=8000)
        except Exception:
            return None
        for p in patterns:
            m = re.search(p, body)
            if m:
                return m.group(1)
        return None

    if not row["title"]:
        for sel in ["h1", "[class*='ItemTitle']", "[class*='itemTitle']", ".tb-detail-hd h1"]:
            try:
                loc = page.locator(sel).first
                if loc.count() > 0:
                    t = loc.inner_text(timeout=5000).strip()
                    if t:
                        row["title"] = t
                        break
            except Exception:
                continue
    if not row["price"]:
        row["price"] = dom_text([r"[¥￥]\s*([\d,]+(?:\.\d{1,2})?)"])
    if not row["sales"]:
        row["sales"] = dom_text([r"已售\s*([\d.,万+]+)", r"月销\s*([\d.,万+]+)", r"总销量[:：]?\s*([\d.,万+]+)"])
    if not row["comments"]:
        row["comments"] = dom_text([r"评价\s*\(?([\d.,万+]+)\)?", r"累计评价\s*([\d.,万+]+)"])

    return row


def stage2_scrape_details(page, urls, dmin, dmax):
    done_ids = set()
    if ITEMS_FILE.exists():
        for line in ITEMS_FILE.read_text("utf-8").splitlines():
            try:
                done_ids.add(json.loads(line)["item_id"])
            except Exception:
                pass
    todo = [u for u in urls if item_id_from_url(u) not in done_ids]
    print(f">> 详情采集：共 {len(urls)} 个商品，已完成 {len(done_ids)}，本次待采 {len(todo)}")

    captured = {}

    def on_response(resp):
        if "mtop.taobao.pcdetail.data.get" in resp.url:
            try:
                captured["detail_json"] = extract_jsonp(resp.text())
            except Exception:
                pass

    page.on("response", on_response)

    fails = 0
    with ITEMS_FILE.open("a", encoding="utf-8") as fout:
        for i, url in enumerate(todo, 1):
            iid = item_id_from_url(url)
            captured.clear()
            print(f"[{i}/{len(todo)}] {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
            except PWTimeout:
                print("    !! 页面加载超时，跳过（下次运行会重试）")
                fails += 1
                continue
            if wait_if_captcha(page) or kicked_to_login(page):
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except PWTimeout:
                    continue
            # 每采十几个商品休息一会儿，模拟真人放下手机的间歇
            if i % random.randint(12, 18) == 0:
                human_pause(30, 90, "阶段性休息，降低风控")
            scroll_page(page, rounds=3)
            row = extract_from_detail(page, captured)
            row.update({"item_id": iid, "url": url, "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")})
            if not row["title"]:
                print("    !! 未提取到标题，可能被拦截或页面结构变化，跳过（下次重试）")
                fails += 1
                if fails >= 5:
                    print("!! 连续失败过多，为安全起见先停止。请稍后（建议数小时后）再运行继续。")
                    break
                continue
            fails = 0
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
            fout.flush()
            print(f"    ✓ {row['title'][:40]} | 价:{row['price']} | 销:{row['sales']} | 评:{row['comments']}")
            human_pause(dmin, dmax, "模拟浏览间隔")
    page.remove_listener("response", on_response)


# ---------------------------------------------------------------- 导出 Excel

def export_excel(exclude_keywords):
    from openpyxl import Workbook

    rows, seen = [], set()
    if not ITEMS_FILE.exists():
        print("!! 还没有采集数据，无法导出。")
        return None
    for line in ITEMS_FILE.read_text("utf-8").splitlines():
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("item_id") in seen:
            continue
        seen.add(r.get("item_id"))
        rows.append(r)

    def is_bundle(title):
        return any(k in (title or "") for k in exclude_keywords)

    singles = [r for r in rows if not is_bundle(r.get("title"))]
    bundles = [r for r in rows if is_bundle(r.get("title"))]

    wb = Workbook()
    header = ["品名", "售价(元)", "销量", "评论数", "产品链接", "商品ID"]

    def fill(ws, data):
        ws.append(header)
        for r in sorted(data, key=lambda x: (x.get("title") or "")):
            price = parse_cn_number(re.sub(r"[¥￥,]", "", str(r.get("price") or ""))) if r.get("price") else None
            ws.append([
                r.get("title"),
                price if price is not None else r.get("price"),
                parse_cn_number(r.get("sales")) if r.get("sales") is not None else None,
                parse_cn_number(r.get("comments")) if r.get("comments") is not None else None,
                r.get("url"),
                r.get("item_id"),
            ])
        for col, w in zip("ABCDEF", [60, 12, 12, 12, 50, 16]):
            ws.column_dimensions[col].width = w

    ws1 = wb.active
    ws1.title = "单品"
    fill(ws1, singles)
    ws2 = wb.create_sheet("已过滤-套包")
    fill(ws2, bundles)

    out = DATA_DIR / f"罗技官方旗舰店_商品数据_{date.today():%Y%m%d}.xlsx"
    wb.save(out)
    print(f">> 导出完成：{out}")
    print(f"   单品 {len(singles)} 条；按关键词过滤出的套包 {len(bundles)} 条（在第二个工作表，可自行核对）")
    return out


# ---------------------------------------------------------------- 主流程

def main():
    ap = argparse.ArgumentParser(description="天猫店铺商品采集（防封号低速版）")
    ap.add_argument("--shop", default="https://logitech.tmall.com", help="店铺首页地址")
    ap.add_argument("--max-pages", type=int, default=60, help="列表页最大翻页数")
    ap.add_argument("--min-delay", type=float, default=6.0, help="动作间最小等待秒数")
    ap.add_argument("--max-delay", type=float, default=12.0, help="动作间最大等待秒数")
    ap.add_argument("--exclude", default=",".join(DEFAULT_EXCLUDE_KEYWORDS),
                    help="套包过滤关键词，逗号分隔")
    ap.add_argument("--no-details", action="store_true", help="只收集商品链接，不进详情页")
    ap.add_argument("--export-only", action="store_true", help="不采集，仅用已有数据导出 Excel")
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    exclude_keywords = [k.strip() for k in args.exclude.split(",") if k.strip()]

    if args.export_only:
        export_excel(exclude_keywords)
        return

    print("=" * 60)
    print("天猫店铺采集启动。将打开一个真实浏览器窗口，请勿关闭。")
    print("采集期间可以最小化窗口，但不要在该窗口里另外操作。")
    print("=" * 60)

    with sync_playwright() as p:
        common = dict(
            headless=False,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=["--disable-blink-features=AutomationControlled"],
        )
        # 优先使用电脑上真实安装的 Edge/Chrome（比自带浏览器更不易被风控识别）。
        # 不同浏览器使用各自的配置目录，切换后需要重新扫码登录一次。
        ctx = None
        for channel in ("msedge", "chrome", None):
            profile = PROFILE_DIR if channel is None else Path(f"{PROFILE_DIR}-{channel}")
            try:
                if channel:
                    ctx = p.chromium.launch_persistent_context(str(profile), channel=channel, **common)
                else:
                    ctx = p.chromium.launch_persistent_context(str(profile), **common)
                print(f">> 使用浏览器：{channel or '自带 Chromium'}")
                break
            except Exception:
                continue
        if ctx is None:
            print("!! 无法启动任何浏览器，请把本窗口截图发给助手。")
            return
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        try:
            ensure_logged_in(page, args.shop)
            urls = stage1_collect_urls(page, args.shop, args.max_pages, args.min_delay, args.max_delay)
            if not args.no_details and urls:
                stage2_scrape_details(page, urls, args.min_delay, args.max_delay)
        except KeyboardInterrupt:
            print("\n>> 已手动中断。进度已保存，下次运行会从断点继续。")
        finally:
            ctx.close()

    export_excel(exclude_keywords)


if __name__ == "__main__":
    main()
