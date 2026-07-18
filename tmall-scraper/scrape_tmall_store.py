# -*- coding: utf-8 -*-
"""
天猫店铺商品数据采集工具（低风险 / 防封号设计）

采集字段：品名、售价、产品链接、销量、评论数
默认目标：天猫罗技官方旗舰店 https://logitech.tmall.com

v2 变更：默认只采集【列表页】——商品卡片上已经有价格/销量/评价数，
不再逐个进详情页，页面访问量从两百多次降到十几次，风控压力大幅降低。
（如列表页没有评价数，可加 --with-details 只对缺失的商品补采详情页。）

防封号策略：
  1. 真实浏览器（持久化登录，扫码一次即可复用）；
  2. 单线程 + 随机等待，模拟真人翻页节奏；
  3. 检测到滑块/被踢下线时暂停，等人工处理后继续；
  4. 断点续采：进度实时保存，可分多次采完。

用法（本地电脑，需要图形界面）：
  pip install -r requirements.txt
  playwright install chromium
  python scrape_tmall_store.py                # 采集并导出 Excel
  python scrape_tmall_store.py --export-only  # 只用已有数据重新导出
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


# ---------------------------------------------------------------- 工具函数

def human_pause(min_s: float, max_s: float, why: str = ""):
    t = random.uniform(min_s, max_s)
    if why:
        print(f"    …等待 {t:.1f}s（{why}）")
    time.sleep(t)


def parse_cn_number(text):
    """把 '2.5万+'、'1000+'、'3万' 之类的文本转成数字（取下限）。"""
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
    """在嵌套 dict/list 中递归查找第一个命中的 key（广度优先）。"""
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


def safe_goto(page, url: str) -> bool:
    """页面跳转，兜住一切异常（超时/被重定向打断等），失败返回 False。"""
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=60000)
        return True
    except Exception as e:
        print(f"    !! 跳转失败：{str(e).splitlines()[0][:100]}")
        return False


def load_done_rows():
    """读取已采集的行，按 item_id 合并（后写入的非空字段覆盖先前的）。"""
    merged = {}
    if ITEMS_FILE.exists():
        for line in ITEMS_FILE.read_text("utf-8").splitlines():
            try:
                r = json.loads(line)
            except Exception:
                continue
            iid = r.get("item_id")
            if not iid:
                continue
            if iid in merged:
                for k, v in r.items():
                    if v not in (None, ""):
                        merged[iid][k] = v
            else:
                merged[iid] = r
    return merged


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
        print("!! 完成后回到这里按回车继续。今天第 3 次出现的话建议收工。")
        print("!" * 60)
        input(">> 验证完成后按回车继续 ")
        time.sleep(2)
        return True
    return False


def kicked_to_login(page) -> bool:
    """被风控踢回登录页时，暂停等待人工重新扫码。返回是否发生过。"""
    if "login.tmall.com" in page.url or "login.taobao.com" in page.url or "login_jump" in page.url:
        print("\n" + "!" * 60)
        print("!! 天猫要求重新登录（风控信号）。请在浏览器窗口重新扫码登录。")
        print("!! 当天第 2 次被踢下线的话，建议直接关闭程序明天再继续，")
        print("!! 进度不会丢。反复硬登会让风控越来越严。")
        print("!" * 60)
        input(">> 重新登录完成后按回车继续，或按 Ctrl+C 退出 ")
        time.sleep(2)
        return True
    return False


def ensure_logged_in(page, shop_url: str):
    safe_goto(page, shop_url)
    wait_if_captcha(page)
    for _ in range(2):
        if "login.tmall.com" in page.url or "login.taobao.com" in page.url:
            print("\n>> 需要登录：请在打开的浏览器窗口里用手机淘宝/天猫 App 扫码登录。")
            print(">> 登录状态会保存，下次运行无需再登录。")
            input(">> 登录完成、看到店铺页面后按回车继续 ")
            safe_goto(page, shop_url)
            wait_if_captcha(page)
        else:
            break
    print(f">> 当前页面：{page.url}")


# ---------------------------------------------------------------- 列表页采集（核心）

def scroll_page(page, rounds=6):
    for _ in range(rounds):
        page.mouse.wheel(0, random.randint(600, 1200))
        time.sleep(random.uniform(0.5, 1.2))


CARD_JS = """
els => els.map(a => {
    let node = a;
    for (let i = 0; i < 6; i++) {
        const p = node.parentElement;
        if (!p) break;
        const links = p.querySelectorAll("a[href*='item.htm']");
        const ids = new Set();
        links.forEach(l => { const m = l.href.match(/[?&]id=(\\d+)/); if (m) ids.add(m[1]); });
        if (ids.size > 1) break;
        node = p;
    }
    return {href: a.href, text: node.innerText || ""};
})
"""


def parse_card_text(text: str):
    """从商品卡片的整体文本里解析 标题/价格/销量/评价数。"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    full = "\n".join(lines)
    row = {"title": None, "price": None, "sales": None, "comments": None}

    m = re.search(r"[¥￥]\s*([\d,]+(?:\.\d{1,2})?)", full)
    if m:
        row["price"] = m.group(1).replace(",", "")
    m = re.search(r"(?:已售|月销|总销量)[:：]?\s*([\d.,万+]+)", full)
    if m:
        row["sales"] = m.group(1)
    m = (re.search(r"([\d.,万+]+)\s*(?:条?评价|人?好评|人评价)", full)
         or re.search(r"(?:评价|评论)\s*[:：(]?\s*([\d.,万+]+)", full))
    if m:
        row["comments"] = m.group(1)

    cands = [l for l in lines
             if len(l) >= 6 and not re.search(r"[¥￥]|已售|月销|评价|评论|优惠|领券|券|包邮|旗舰店|保障|分期|^\d+[.\d]*$", l)]
    if cands:
        row["title"] = max(cands, key=len)
    return row


def collect_cards_on_page(page):
    """返回 {item_id: row} —— 从当前列表页的商品卡片直接解析数据。"""
    result = {}
    try:
        cards = page.eval_on_selector_all(
            "a[href*='detail.tmall.com/item'], a[href*='item.taobao.com/item'], a[href*='chaoshi.detail.tmall.com/item']",
            CARD_JS,
        )
    except Exception:
        return result
    for c in cards:
        iid = item_id_from_url(c["href"])
        if not iid:
            continue
        row = parse_card_text(c.get("text") or "")
        row["item_id"] = iid
        row["url"] = f"https://detail.tmall.com/item.htm?id={iid}"
        old = result.get(iid)
        # 同一商品可能有多个链接（图片/标题各一个），保留信息最全的解析结果
        if not old or sum(v is not None for v in row.values()) > sum(v is not None for v in old.values()):
            result[iid] = row
    return result


def click_next_page(page) -> bool:
    candidates = [
        "a.J_SearchAsync.next",
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


def stage1_collect(page, shop_url, max_pages, dmin, dmax):
    """翻列表页，直接把卡片数据写入 ITEMS_FILE。"""
    done = load_done_rows()
    all_ids = set(done.keys())
    print(f">> 已有 {len(all_ids)} 条商品记录（断点续采）。")

    origin = f"https://{urlparse(shop_url).netloc}"
    list_entries = [f"{origin}/search.htm", f"{origin}/category.htm", shop_url]

    fout = ITEMS_FILE.open("a", encoding="utf-8")

    def save_cards(cards):
        new_cnt = 0
        for iid, row in cards.items():
            old = done.get(iid)
            # 新商品，或本次解析出了旧记录缺失的字段，都写一条（导出时合并）
            if not old or any(row.get(k) and not old.get(k) for k in ("title", "price", "sales", "comments")):
                row["scraped_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
                fout.write(json.dumps(row, ensure_ascii=False) + "\n")
                fout.flush()
                if not old:
                    new_cnt += 1
                merged = dict(old or {})
                merged.update({k: v for k, v in row.items() if v not in (None, "")})
                done[iid] = merged
        return new_cnt

    entry_ok = None
    for entry in list_entries:
        if not safe_goto(page, entry):
            continue
        wait_if_captcha(page)
        kicked_to_login(page)
        scroll_page(page)
        cards = collect_cards_on_page(page)
        print(f">> 入口 {entry} ：本页发现 {len(cards)} 个商品")
        if cards:
            entry_ok = entry
            n = save_cards(cards)
            print(f">> 第 1 页入库，新增 {n} 个商品")
            break
    if not entry_ok:
        print("!! 没能在店铺页面上找到商品，请截图反馈。")
        fout.close()
        return done

    stale_rounds = 0
    for page_no in range(2, max_pages + 1):
        human_pause(dmin, dmax, f"准备第 {page_no} 页")
        moved = False
        if "search.htm" in entry_ok:
            moved = safe_goto(page, f"{entry_ok}?pageNo={page_no}")
        if not moved:
            moved = click_next_page(page)
        if not moved:
            print(">> 没有下一页了，采集结束。")
            break
        if wait_if_captcha(page) or kicked_to_login(page):
            safe_goto(page, f"{entry_ok}?pageNo={page_no}" if "search.htm" in entry_ok else entry_ok)
        scroll_page(page)
        cards = collect_cards_on_page(page)
        before = len(done)
        save_cards(cards)
        new = len(done) - before
        print(f">> 第 {page_no} 页：{len(cards)} 个商品，新增 {new} 个（累计 {len(done)}）")
        stale_rounds = stale_rounds + 1 if new == 0 else 0
        if stale_rounds >= 2:
            print(">> 连续两页没有新商品，认为已到最后一页。")
            break

    fout.close()
    URLS_FILE.write_text(json.dumps([r["url"] for r in done.values()], ensure_ascii=False, indent=1), "utf-8")
    got_comments = sum(1 for r in done.values() if r.get("comments"))
    print(f">> 列表采集完成：共 {len(done)} 个商品，其中 {got_comments} 个带评价数。")
    return done


# ---------------------------------------------------------------- 详情页补采（可选）

def extract_from_detail(page, captured: dict) -> dict:
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

    if not row["sales"]:
        row["sales"] = dom_text([r"已售\s*([\d.,万+]+)", r"月销\s*([\d.,万+]+)"])
    if not row["comments"]:
        row["comments"] = dom_text([r"(?:累计)?评价\s*\(?([\d.,万+]+)\)?"])
    return row


def stage2_fill_details(page, done, dmin, dmax):
    todo = [r for r in done.values() if not r.get("comments")]
    print(f">> 详情页补采评价数：待补 {len(todo)} 个商品")
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
        for i, base in enumerate(todo, 1):
            url, iid = base["url"], base["item_id"]
            captured.clear()
            print(f"[{i}/{len(todo)}] {url}")
            if not safe_goto(page, url):
                fails += 1
                if fails >= 5:
                    print("!! 连续失败过多，停止详情补采（列表数据不受影响）。")
                    break
                continue
            if wait_if_captcha(page) or kicked_to_login(page):
                if not safe_goto(page, url):
                    continue
            scroll_page(page, rounds=3)
            row = extract_from_detail(page, captured)
            patch = {k: v for k, v in row.items() if v not in (None, "")}
            if patch:
                fails = 0
                patch.update({"item_id": iid, "url": url,
                              "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S")})
                fout.write(json.dumps(patch, ensure_ascii=False) + "\n")
                fout.flush()
                print(f"    ✓ 补到：{ {k: v for k, v in patch.items() if k in ('sales', 'comments')} }")
            else:
                fails += 1
                if fails >= 5:
                    print("!! 连续失败过多，停止详情补采（列表数据不受影响）。")
                    break
            if i % random.randint(12, 18) == 0:
                human_pause(30, 90, "阶段性休息，降低风控")
            else:
                human_pause(dmin, dmax, "模拟浏览间隔")
    page.remove_listener("response", on_response)


# ---------------------------------------------------------------- 导出 Excel

def export_excel(exclude_keywords):
    from openpyxl import Workbook

    done = load_done_rows()
    rows = [r for r in done.values() if r.get("title")]
    if not rows:
        print("!! 还没有采集到带标题的数据，无法导出。")
        return None

    def is_bundle(title):
        return any(k in (title or "") for k in exclude_keywords)

    singles = [r for r in rows if not is_bundle(r.get("title"))]
    bundles = [r for r in rows if is_bundle(r.get("title"))]

    wb = Workbook()
    header = ["品名", "售价(元)", "销量", "评论数", "产品链接", "商品ID"]

    def fill(ws, data):
        ws.append(header)
        for r in sorted(data, key=lambda x: (x.get("title") or "")):
            price = r.get("price")
            try:
                price = float(re.sub(r"[¥￥,]", "", str(price))) if price else None
            except ValueError:
                pass
            ws.append([
                r.get("title"),
                price,
                parse_cn_number(r.get("sales")),
                parse_cn_number(r.get("comments")),
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
    print(f"   单品 {len(singles)} 条；按关键词过滤出的套包 {len(bundles)} 条（第二个工作表可核对）")
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
    ap.add_argument("--with-details", action="store_true",
                    help="对缺少评价数的商品进详情页补采（页面访问量大，谨慎使用）")
    ap.add_argument("--export-only", action="store_true", help="不采集，仅用已有数据导出 Excel")
    args = ap.parse_args()

    DATA_DIR.mkdir(exist_ok=True)
    exclude_keywords = [k.strip() for k in args.exclude.split(",") if k.strip()]

    if args.export_only:
        export_excel(exclude_keywords)
        return

    print("=" * 60)
    print("天猫店铺采集启动（列表页模式）。将打开真实浏览器窗口，请勿关闭。")
    print("=" * 60)

    with sync_playwright() as p:
        common = dict(
            headless=False,
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            args=["--disable-blink-features=AutomationControlled"],
        )
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
            print("!! 无法启动任何浏览器，请截图反馈。")
            return
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

        try:
            ensure_logged_in(page, args.shop)
            done = stage1_collect(page, args.shop, args.max_pages, args.min_delay, args.max_delay)
            if args.with_details and done:
                stage2_fill_details(page, done, args.min_delay, args.max_delay)
        except KeyboardInterrupt:
            print("\n>> 已手动中断。进度已保存，下次运行会从断点继续。")
        except Exception as e:
            print(f"\n!! 出现未预期的错误：{e}")
            print(">> 进度已保存。请把本窗口截图发给助手。")
        finally:
            try:
                ctx.close()
            except Exception:
                pass

    export_excel(exclude_keywords)


if __name__ == "__main__":
    main()
