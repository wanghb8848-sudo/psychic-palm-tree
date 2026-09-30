python3 - <<'PY'
import urllib.request, urllib.parse, json, re, time, concurrent.futures as cf
KW = {'m221':'m221','m275':'m275','m280':'m280','b175':'b175','m91p':'m91p','c920e':'c920e','zone-wireless':'zone-wireless','zone-wired':'zone-wired',
 'zone-earbuds':'earbuds','zone-tws':'zone-true-wireless','h570e':'h570e','logi-dock':'logi-dock','mic':'mic-pod','pro-x3':'superstrike','g304x':'g304x',
 'g316':'g316','g517':'g517','g435':'g435','a50':'a50','m100r':'m100r','m110':'m110','mk120':'mk120','spotlight2':'spotlight-2','keys-to-go2':'keys-to-go',
 'mx-brio':'mx-brio','mx-master-4':'mx-master-4','expansion':'expansion-mic'}
HOSTS = ['www.logitech.com/zh-cn/products/', 'www.logitech.com.cn/zh-cn/products/', 'www.logitech.com/zh-cn/shop/p/', 'www.logitech.com/en-us/shop/p/', 'www.logitech.com/en-us/products/']
def get(u, t=90):
    req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
    return urllib.request.urlopen(req, timeout=t).read().decode('utf8', 'ignore')
def cdx(host, kw):
    q = urllib.parse.urlencode({'url': host, 'matchType': 'prefix', 'output': 'json', 'filter': ['statuscode:200', f'original:.*{kw}.*'], 'collapse': 'urlkey', 'limit': '40', 'fl': 'timestamp,original'}, doseq=True)
    for i in range(3):
        try:
            d = json.loads(get('http://web.archive.org/cdx/search/cdx?' + q) or '[]'); return d[1:]
        except Exception as e: err = str(e); time.sleep(5)
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
        if base in seen or len(seen) >= 10: continue
        seen.add(base)
        try:
            h = get(f'http://web.archive.org/web/{r[0]}id_/{r[1]}')
            got.append(dict(ts=r[0], url=r[1], **extract(h)))
        except Exception as e:
            got.append({'url': r[1], 'err': str(e)[:80]})
    return kw, got
with cf.ThreadPoolExecutor(8) as ex:
    for kw, got in ex.map(job, KW):
        res[kw] = got
json.dump(res, open('wb/skus.json', 'w'), ensure_ascii=False, indent=0)
# live en-us / zh-cn pages
live = {}
for u in ['https://www.logitech.com/en-us/products/headsets/h570e-usb-noise-cancelling.html', 'https://www.logitech.com/en-us/shop/p/logi-dock', 'https://www.logitech.com/en-us/shop/p/pro-x3-superstrike-mouse',
          'https://www.logitech.com/en-us/shop/p/mx-master-4', 'https://www.logitech.com/en-us/shop/p/mx-brio-4k-webcam', 'https://www.logitech.com/en-us/shop/p/spotlight-2-presenter-remote',
          'https://www.logitech.com/en-us/shop/p/keys-to-go2-universal', 'https://www.logitech.com/en-us/shop/p/mk120-usb-keyboard-mouse', 'https://www.logitech.com/en-us/shop/p/a50-x-astro-wireless-headset',
          'https://www.logitech.com/zh-cn/shop/p/mx-master-4', 'https://www.logitech.com/zh-cn/shop/p/g304-lightspeed-wireless-gaming-mouse']:
    try: live[u] = extract(get(u, 60))
    except Exception as e: live[u] = {'err': str(e)[:80]}
json.dump(live, open('wb/live.json', 'w'), ensure_ascii=False, indent=0)
PY
