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
import os
import random
import re
import subprocess
import sys
import tempfile
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
VARIANTS_FILE = DATA_DIR / "variants.jsonl"  # 每个颜色/款式一行：{item_id, name, url, img}

# 标题中出现这些词的商品视为“套包/套装”，会被移到 Excel 的第二个工作表，不计入单品
DEFAULT_EXCLUDE_KEYWORDS = ["套装", "套餐", "组合", "礼盒", "礼包", "套包", "两件装", "二件装", "件套"]


# ---------------------------------------------------------------- 工具函数

def human_pause(min_s: float, max_s: float, why: str = ""):
    t = random.uniform(min_s, max_s)
    if why:
        print(f"    …等待 {t:.1f}s（{why}）")
    time.sleep(t)


def normalize_price(raw):
    """把任意来源的价格统一成“元”的浮点数。
    天猫价格恒为两位小数，OCR/接口常把 129.00 读成/存成 12900（丢了小数点），
    导致“几百变几万”。规则：带小数点的当元直接用；纯整数（>=3位）视为“分”，除以 100。
    这是所有价格的总兜底，不管价格来自 OCR、卡片文字还是接口 JSON 都在这里归一。"""
    if raw is None or raw == "":
        return None
    s = re.sub(r"[¥￥,\s]", "", str(raw))
    if not s:
        return None
    if "." in s:
        m = re.match(r"^\d+\.\d{1,2}", s)
        return float(m.group(0)) if m else None
    m = re.match(r"^\d+", s)
    if not m:
        return None
    digits = m.group(0)
    return round(int(digits) / 100, 2) if len(digits) >= 3 else float(digits)


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
    const pick = (root, sels) => {
        for (const s of sels) {
            const el = root.querySelector(s);
            if (el && el.innerText && el.innerText.trim()) return el.innerText.trim();
        }
        return "";
    };
    return {
        href: a.href,
        text: node.innerText || "",
        t_title: pick(node, ["[class*='title' i]", "[class*='name' i]"]),
        t_price: pick(node, ["[class*='price' i]"]),
        t_sold: pick(node, ["[class*='sold' i]", "[class*='sale' i]", "[class*='deal' i]"]),
        t_comment: pick(node, ["[class*='comment' i]", "[class*='rate' i]", "[class*='eval' i]"]),
    };
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
    else:
        # 卡片上 ¥ 符号可能是图标而非文字：找带两位小数或带“元”的独立数字行
        for l in lines:
            m = re.match(r"^(\d{1,6}\.\d{1,2})\s*(?:元|起)?$", l.replace(",", ""))
            if m:
                row["price"] = m.group(1)
                break
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


ITEM_LINK_SEL = ("a[href*='detail.tmall.com/item'], a[href*='item.taobao.com/item'], "
                 "a[href*='chaoshi.detail.tmall.com/item']")

# 找到某商品卡片里“最主要”的价格元素（字号最大的那个），用于截图 OCR
PRICE_EL_JS = """
a => {
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
    const cands = [...node.querySelectorAll("[class*='price' i]")]
        .filter(c => { const r = c.getBoundingClientRect(); return r.width > 1 && r.height > 1; });
    if (!cands.length) return null;
    let best = cands[0], bestFs = -1;
    cands.forEach(c => {
        const fs = parseFloat(getComputedStyle(c).fontSize) || 0;
        if (fs > bestFs) { bestFs = fs; best = c; }
    });
    return best;
}
"""


def ocr_prices_on_page(page, ocr):
    """对每个商品卡片的价格元素截图并 OCR，破解字体加密。返回 {item_id: price}。"""
    out = {}
    if ocr is None:
        return out
    try:
        handles = page.query_selector_all(ITEM_LINK_SEL)
    except Exception:
        return out
    for a in handles:
        try:
            iid = item_id_from_url(a.get_attribute("href") or "")
            if not iid or iid in out:
                continue
            el = a.evaluate_handle(PRICE_EL_JS).as_element()
            if not el:
                continue
            png = el.screenshot()
            txt = (ocr.classification(png) or "").replace(" ", "").replace(",", "")
            m = re.search(r"\d+(?:\.\d{1,2})?", txt)
            if m:
                # 原样存 OCR 识别到的数字串（可能没小数点，如 12900）；
                # 统一由导出时的 normalize_price 归一成“元”，避免多处各除一次。
                out[iid] = m.group(0)
        except Exception:
            continue
    return out


def collect_cards_on_page(page):
    """返回 {item_id: row} —— 结构化子元素（学后羿）优先，整卡文字正则兜底。"""
    result = {}
    try:
        cards = page.eval_on_selector_all(ITEM_LINK_SEL, CARD_JS)
    except Exception:
        return result
    for c in cards:
        iid = item_id_from_url(c["href"])
        if not iid:
            continue
        row = parse_card_text(c.get("text") or "")
        # 结构化子元素的结果优先覆盖正则结果
        t = (c.get("t_title") or "").strip()
        if len(t) >= 6 and not re.search(r"[¥￥]|已售|评价", t):
            row["title"] = t
        m = re.search(r"([\d,]+(?:\.\d{1,2})?)", (c.get("t_price") or "").replace("¥", "").replace("￥", ""))
        if m:
            row["price"] = m.group(1).replace(",", "")
        m = re.search(r"([\d.,万+]+)", c.get("t_sold") or "")
        if m:
            row["sales"] = m.group(1)
        m = re.search(r"([\d.,万+]+)", c.get("t_comment") or "")
        if m:
            row["comments"] = m.group(1)
        row["item_id"] = iid
        row["url"] = f"https://detail.tmall.com/item.htm?id={iid}"
        old = result.get(iid)
        # 同一商品可能有多个链接（图片/标题各一个），保留信息最全的解析结果
        if not old or sum(v is not None for v in row.values()) > sum(v is not None for v in old.values()):
            result[iid] = row
    return result


# ---------------- 颜色/款式变体：从列表页卡片那排小图直接抓“变体网址”（不进详情页）
# 逻辑同后羿/八爪鱼：在每个商品卡片内部，收集那排缩略图对应的全部 item.htm 链接，
# 每个颜色/款式往往带独立的 &skuId=/&sku_properties=，即“一个小分类一个网址”。
VARIANT_JS = r"""
els => {
    const out = {};
    els.forEach(a => {
        let node = a;
        for (let i = 0; i < 6; i++) {
            const p = node.parentElement;
            if (!p) break;
            const ids = new Set();
            p.querySelectorAll("a[href*='item.htm']").forEach(l => {
                const m = l.href.match(/[?&]id=(\d+)/); if (m) ids.add(m[1]);
            });
            if (ids.size > 1) break;   // 再往上就并进别的商品了，停
            node = p;
        }
        const base = (a.href.match(/[?&]id=(\d+)/) || [])[1] || "";
        if (!base || out[base]) return;
        // 收集卡片内所有指向商品页的链接（含缩略图外链），按 href 去重
        const seen = new Set();
        const list = [];
        node.querySelectorAll("a[href*='item.htm']").forEach(l => {
            const href = l.href;
            if (seen.has(href)) return; seen.add(href);
            const img = l.querySelector("img");
            list.push({
                href: href,
                name: ((img && (img.alt || img.title)) || l.getAttribute("title") || "").trim(),
                img: img ? (img.src || img.getAttribute("data-src") || "") : "",
                sku: /[?&](skuId|sku_properties|skuid)=/.test(href),
            });
        });
        // 缩略图本身可能不是外链，而是纯 <img>（点击才切图）——把它们也抓出来当诊断
        const thumbs = [];
        node.querySelectorAll("img").forEach(im => {
            const nm = (im.alt || im.title || "").trim();
            const src = im.src || im.getAttribute("data-src") || "";
            if (src) thumbs.push({ name: nm, img: src });
        });
        out[base] = { links: list, thumbs: thumbs };
    });
    return out;
}
"""


def harvest_variants_on_page(page):
    """返回 {item_id: [{name,url,img}]} —— 每个颜色/款式的独立网址。
    优先取“带 skuId 的独立链接”；若卡片里所有链接都指向同一个商品页（无独立
    变体网址），则该商品不产出变体行（说明这排小图是纯 JS 切图，列表页无独立网址）。"""
    out = {}
    try:
        raw = page.eval_on_selector_all(ITEM_LINK_SEL, VARIANT_JS)
    except Exception:
        return out
    for iid, info in (raw or {}).items():
        links = info.get("links") or []
        base_url = f"https://detail.tmall.com/item.htm?id={iid}"
        variants = []
        seen = set()
        # 带 skuId 的链接才是真正的“颜色/款式独立网址”
        sku_links = [l for l in links if l.get("sku")]
        for l in sku_links:
            u = l.get("href")
            if u and u not in seen:
                seen.add(u)
                variants.append({"name": l.get("name") or "", "url": u, "img": l.get("img") or ""})
        # 没有带 skuId 的独立链接时，退而记录缩略图（有几个颜色 + 图URL），网址用商品页兜底
        if not variants:
            thumbs = info.get("thumbs") or []
            # 去掉重复图；只有 >=2 张才算“有多个变体”
            uniq = []
            tseen = set()
            for t in thumbs:
                if t["img"] and t["img"] not in tseen:
                    tseen.add(t["img"])
                    uniq.append(t)
            if len(uniq) >= 2:
                for t in uniq:
                    variants.append({"name": t.get("name") or "", "url": base_url, "img": t["img"]})
        if variants:
            out[iid] = variants
    return out


def load_variants():
    """读取已采集的变体行，按 item_id 归组。"""
    grouped = {}
    if VARIANTS_FILE.exists():
        for line in VARIANTS_FILE.read_text("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            grouped.setdefault(r.get("item_id"), {})[r.get("url")] = r
    return grouped


# ---------------- 来源三：偷听页面自己加载的接口 JSON（数据最干净）

def _price_val(v, depth=0):
    """判断一个值是不是像“价格”，是就规整成字符串返回。"""
    if isinstance(v, (int, float)) and 0 < v < 10 ** 6:
        return str(v)
    if isinstance(v, str):
        s = v.strip().lstrip("¥￥").replace(",", "")
        m = re.match(r"^(\d{1,6}(?:\.\d{1,2})?)", s)
        if m:
            return m.group(1)
    if isinstance(v, (dict, list)) and depth < 4:
        return _hunt_price(v, depth + 1)
    return None


def _hunt_price(obj, depth=0):
    """在商品对象子树里找任何字段名含 price/money/yuan 的价格值。"""
    if depth > 4:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            if any(w in k.lower() for w in ("price", "money", "yuan")):
                got = _price_val(v, depth)
                if got:
                    return got
        for v in obj.values():
            if isinstance(v, (dict, list)):
                got = _hunt_price(v, depth + 1)
                if got:
                    return got
    elif isinstance(obj, list):
        for v in obj:
            got = _hunt_price(v, depth + 1)
            if got:
                return got
    return None


def harvest_api_items(data):
    """在任意接口返回的嵌套 JSON 里挖商品对象（有 itemId+title 的 dict）。"""
    found = {}
    queue = [data]
    while queue:
        cur = queue.pop()
        if isinstance(cur, dict):
            iid = cur.get("itemId") or cur.get("item_id") or cur.get("nid")
            title = cur.get("title") or cur.get("itemTitle") or cur.get("itemName")
            if iid and title and str(iid).isdigit() and isinstance(title, str) and len(title) >= 6:
                price = _hunt_price(cur)
                sales = (cur.get("vagueSellCount") or cur.get("soldQuantity") or cur.get("sellCount")
                         or cur.get("sold") or cur.get("annualVol") or cur.get("monthSellCount"))
                comments = cur.get("commentCount") or cur.get("rateCount") or cur.get("commentNum")
                found[str(iid)] = {
                    "item_id": str(iid),
                    "title": title.strip(),
                    "price": str(price) if price not in (None, "") else None,
                    "sales": str(sales) if sales not in (None, "") else None,
                    "comments": str(comments) if comments not in (None, "") else None,
                    "url": f"https://detail.tmall.com/item.htm?id={iid}",
                }
            queue.extend(cur.values())
        elif isinstance(cur, list):
            queue.extend(cur)
    return found


def merge_sources(cards, api_items):
    """卡片解析结果与接口结果按商品 ID 合并；接口值补齐缺失字段。"""
    out = {k: dict(v) for k, v in cards.items()}
    for iid, row in api_items.items():
        if iid in out:
            for k, v in row.items():
                if v not in (None, "") and not out[iid].get(k):
                    out[iid][k] = v
        else:
            out[iid] = dict(row)
    return out


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


def stage1_collect(page, shop_url, max_pages, dmin, dmax, ocr=None):
    """翻列表页，三路数据源合并后写入 ITEMS_FILE。"""
    done = load_done_rows()
    print(f">> 已有 {len(done)} 条商品记录（断点续采）。")

    # 来源三：监听页面自己发出的接口请求，捡里面的商品 JSON
    api_items = {}

    def on_response(resp):
        url = resp.url
        if not any(k in url for k in ("mtop.", "asyncSearch", "asynSearch", "shopitem", "search")):
            return
        try:
            body = resp.text()
            if "itemId" not in body and "item_id" not in body and "nid" not in body:
                return
            got = harvest_api_items(extract_jsonp(body))
            if got:
                api_items.update(got)
        except Exception:
            pass

    page.on("response", on_response)

    origin = f"https://{urlparse(shop_url).netloc}"
    list_entries = [f"{origin}/search.htm", f"{origin}/category.htm", shop_url]

    fout = ITEMS_FILE.open("a", encoding="utf-8")

    # 变体（颜色/款式）网址：一个颜色一行，按 item_id + url 去重续采
    seen_variants = load_variants()
    fvar = VARIANTS_FILE.open("a", encoding="utf-8")

    def save_variants(page):
        vmap = harvest_variants_on_page(page)
        added = 0
        for iid, vlist in vmap.items():
            bucket = seen_variants.setdefault(iid, {})
            for v in vlist:
                url = v.get("url")
                if url and url not in bucket:
                    rec = {"item_id": iid, "name": v.get("name") or "",
                           "url": url, "img": v.get("img") or ""}
                    bucket[url] = rec
                    fvar.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    fvar.flush()
                    added += 1
        return added

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
        cards = merge_sources(collect_cards_on_page(page), api_items)
        prices = ocr_prices_on_page(page, ocr)
        for iid, pr in prices.items():
            if iid in cards and pr:
                cards[iid]["price"] = pr
        print(f">> 入口 {entry} ：本页发现 {len(cards)} 个商品"
              f"（接口 {len(api_items)} 条，OCR 识别价格 {len(prices)} 个）")
        if cards:
            entry_ok = entry
            n = save_cards(cards)
            nv = save_variants(page)
            print(f">> 第 1 页入库，新增 {n} 个商品，{nv} 个颜色/款式变体网址")
            # 诊断文件：字段缺失时把它发给助手，即可精准修复解析规则
            try:
                raw = page.eval_on_selector_all(ITEM_LINK_SEL, CARD_JS)[:6]
                var_raw = page.eval_on_selector_all(ITEM_LINK_SEL, VARIANT_JS)
                var_sample = dict(list(var_raw.items())[:6]) if isinstance(var_raw, dict) else var_raw
                (DATA_DIR / "debug_first_page.json").write_text(
                    json.dumps({"cards": raw, "api_sample": list(api_items.values())[:3],
                                "variants": var_sample},
                               ensure_ascii=False, indent=1), "utf-8")
            except Exception:
                pass
            break
    if not entry_ok:
        print("!! 没能在店铺页面上找到商品，请截图反馈。")
        page.remove_listener("response", on_response)
        fout.close()
        fvar.close()
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
        cards = merge_sources(collect_cards_on_page(page), api_items)
        prices = ocr_prices_on_page(page, ocr)
        for iid, pr in prices.items():
            if iid in cards and pr:
                cards[iid]["price"] = pr
        before = len(done)
        save_cards(cards)
        nv = save_variants(page)
        new = len(done) - before
        print(f">> 第 {page_no} 页：{len(cards)} 个商品，新增 {new} 个（累计 {len(done)}），"
              f"变体网址 +{nv}")
        stale_rounds = stale_rounds + 1 if new == 0 else 0
        if stale_rounds >= 2:
            print(">> 连续两页没有新商品，认为已到最后一页。")
            break

    page.remove_listener("response", on_response)
    fout.close()
    fvar.close()
    URLS_FILE.write_text(json.dumps([r["url"] for r in done.values()], ensure_ascii=False, indent=1), "utf-8")
    got_comments = sum(1 for r in done.values() if r.get("comments"))
    total_var = sum(len(v) for v in seen_variants.values())
    print(f">> 列表采集完成：共 {len(done)} 个商品，其中 {got_comments} 个带评价数；"
          f"颜色/款式变体网址共 {total_var} 条（{len(seen_variants)} 个商品有变体）。")
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
            price = normalize_price(r.get("price"))
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

    # 变体明细：每个颜色/款式一行，带它自己的网址（不进详情页，取自列表页小图链接）
    variants = load_variants()
    if variants:
        title_by_id = {r.get("item_id"): r.get("title") for r in rows}
        ws3 = wb.create_sheet("颜色款式变体")
        vheader = ["品名", "颜色/款式", "变体网址", "缩略图", "商品ID"]
        ws3.append(vheader)
        for iid in sorted(variants, key=lambda i: (title_by_id.get(i) or "")):
            for v in variants[iid].values():
                ws3.append([
                    title_by_id.get(iid) or "",
                    v.get("name") or "",
                    v.get("url") or "",
                    v.get("img") or "",
                    iid,
                ])
        for col, w in zip("ABCDE", [50, 20, 55, 55, 16]):
            ws3.column_dimensions[col].width = w
        print(f">> 变体明细：{sum(len(v) for v in variants.values())} 条（{len(variants)} 个商品有颜色/款式）")

    # 表格直接放在程序旁边（不是 data 子文件夹），打开程序所在文件夹就能看到
    out = BASE_DIR / f"罗技官方旗舰店_商品数据_{date.today():%Y%m%d}.xlsx"
    try:
        wb.save(out)
    except PermissionError:
        # 上一份表格正被 Excel/WPS 打开占用：换个名字保存，不让成果丢失
        out = BASE_DIR / f"罗技官方旗舰店_商品数据_{date.today():%Y%m%d}_{int(time.time())}.xlsx"
        wb.save(out)
    print("=" * 60)
    print(f">> 导出完成！表格文件在：\n   {out.resolve()}")
    print(f"   单品 {len(singles)} 条；按关键词过滤出的套包 {len(bundles)} 条（第二个工作表可核对）")
    print("=" * 60)
    reveal_in_file_manager(out)
    return out


def reveal_in_file_manager(path):
    """跑完自动弹出文件夹并选中成果表格，避免用户找不到文件。"""
    try:
        p = str(Path(path).resolve())
        if sys.platform.startswith("win"):
            subprocess.Popen(["explorer", "/select,", p])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", p])
    except Exception:
        pass  # 弹不出也不影响成果，路径已在上方打印


# ---------------------------------------------------------------- 主流程

def warn_if_running_from_zip():
    """在压缩包里直接双击运行时，Windows 会把程序解压到隐藏的临时目录执行，
    成果文件会生成在临时目录里害用户找不到。检测到这种情况就拦下并提示。"""
    try:
        base = str(BASE_DIR).lower()
        tmp = tempfile.gettempdir().lower()
        temp_markers = [tmp, "\\temp\\", "/temp/", "appdata\\local\\temp"]
        if any(m in base for m in temp_markers if m):
            print("=" * 60)
            print("!! 检测到程序是【没解压、直接在压缩包里】运行的！")
            print("   这样成果表格会生成在系统临时目录里，很难找到。")
            print("")
            print("   正确做法：")
            print("   1. 右键 zip 压缩包 → 「全部解压缩…」→ 解压到 下载 或 桌面")
            print("   2. 打开解压出来的文件夹，双击 RUN-Windows.bat 运行")
            print("=" * 60)
            input("按回车退出，去解压后重新运行……")
            sys.exit(1)
    except SystemExit:
        raise
    except Exception:
        pass


def main():
    warn_if_running_from_zip()
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

    # 价格 OCR：破解天猫价格字体加密（把价格截图识别成数字）
    ocr = None
    try:
        import ddddocr
        ocr = ddddocr.DdddOcr(show_ad=False)
        print(">> 价格识别（OCR）已就绪。")
    except Exception:
        print("!! 未能加载价格 OCR 组件，本次价格列可能为空（其他字段不受影响）。")
        print("   如需价格，请确保安装成功：pip install ddddocr")

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
            done = stage1_collect(page, args.shop, args.max_pages, args.min_delay, args.max_delay, ocr)
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
