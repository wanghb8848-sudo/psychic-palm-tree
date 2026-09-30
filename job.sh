python3 - <<'PY'
import urllib.request, urllib.parse, json, re, time, concurrent.futures as cf
KW = {'m275':'m275','b175':'b175','m91p':'m91p','zone-wired':'zone-wired[.-][n0-9h]','h570e':'h570e','mic':'expansion-mic','g316':'g316','g517':'g517','g304x-sl':'g304-x-superlight|g304x-superlight','zone-wireless':'zone-wireless[.-][^2]','cc5000e':'mic-pod','pro-x3':'superstrike'}
HOSTS = ['www.logitech.com/zh-cn/product/', 'www.logitech.com.cn/zh-cn/product/', 'www.logitechg.com/zh-cn/products/', 'www.logitechg.com.cn/zh-cn/products/', 'www.logitech.com/zh-cn/products/', 'www.logitech.com.cn/zh-cn/products/', 'www.logitech.com/zh-cn/shop/p/']
def get(u, t=90):
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=t).read().decode('utf8', 'ignore')
def cdx(host, kw):
    q = urllib.parse.urlencode({'url': host, 'matchType': 'prefix', 'output': 'json', 'filter': ['statuscode:200', f'original:.*({kw}).*'], 'collapse': 'urlkey', 'limit': '40', 'fl': 'timestamp,original'}, doseq=True)
    for i in range(5):
        try:
            time.sleep(4)
            d = json.loads(get('http://web.archive.org/cdx/search/cdx?' + q) or '[]'); return d[1:]
        except Exception as e: err = str(e); time.sleep(20 * (i + 1))
    return [['ERR', err]]
def extract(h):
    out = {}
    out['serial'] = [(re.sub(r'\s+', ' ', a).strip(' :'), b) for a, b in re.findall(r'<strong>([^<]*)</strong>\s*<span class="serial-num">(\d{3}-\d{6})</span>', h)]
    pn = re.search(r'name="search_partnumber" content="([^"]*)"', h); out['pn'] = pn.group(1) if pn else ''
    out['models'] = re.findall(r'"@type":\s*"ProductModel"[^{}]{0,400}?"name":\s*"([^"]*)"[^{}]{0,200}?"color":\s*"([^"]*)"', h)
    out['ldsku'] = re.findall(r'"color":\s*"([^"]*)"(?:[^{}]{0,3000}?)"sku":\s*"(\d{3}-\d{6})"', h)
    out['facets'] = re.findall(r'"(\d{3}-\d{6})":\{name:"([^"]*)".{0,20000}?facets:\{color:\{label:"([^"]*)"', h)[:40]
    out['swatch'] = re.findall(r'title="([^"]*)"[^>]*data-variant-skus="([^"]*)"', h)
    out['ctx'] = [re.sub(r'\s+', ' ', h[max(0, m.start()-160):m.start()+40]) for m in re.finditer(r'\d{3}-\d{6}', h)][:60]
    return out
res = {}
def job(kw):
    rows = []
    for host in HOSTS:
        for r in cdx(host, KW[kw]):
            rows.append(r)
    got = []
    seen = set()
    for r in sorted(rows, key=lambda x: x[0], reverse=True):
        if r[0] == 'ERR': got.append({'err': r[1]}); continue
        base = re.sub(r'[?#].*', '', r[1]).lower()
        if base in seen or len(seen) >= 5: continue
        seen.add(base)
        for i in range(4):
            try:
                time.sleep(4)
                h = get(f'http://web.archive.org/web/{r[0]}id_/{r[1]}')
                got.append(dict(ts=r[0], url=r[1], **extract(h))); break
            except Exception as e:
                if i == 3: got.append({'url': r[1], 'err': str(e)[:80]})
                time.sleep(20 * (i + 1))
    return kw, got
with cf.ThreadPoolExecutor(2) as ex:
    for kw, got in ex.map(job, KW):
        res[kw] = got
json.dump(res, open('wb/skus3.json', 'w'), ensure_ascii=False, indent=0)
PY
