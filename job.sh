python3 - <<'PY'
import urllib.request,json,re
d=json.load(open('wb/g333.json'))
out=[]
for ts,orig in d['rows'][:6]:
    try:
        req=urllib.request.Request(f'http://web.archive.org/web/{ts}id_/{orig}',headers={'User-Agent':'Mozilla/5.0'})
        h=urllib.request.urlopen(req,timeout=60).read().decode('utf8','ignore')
        out+=re.findall(r'https?://[^"\s]+\.(?:png|jpg)',h)
    except Exception as e: out.append('ERR '+str(e)[:60])
json.dump(sorted(set(out)),open('wb/g333b.json','w'),indent=1)
PY
