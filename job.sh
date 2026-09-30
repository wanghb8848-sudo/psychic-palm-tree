python3 - <<'PY'
import urllib.request,json,re,time
def get(u,t=60):
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    return urllib.request.urlopen(req,timeout=t).read().decode('utf8','ignore')
out={}
try:
    u='http://web.archive.org/cdx/search/cdx?url=www.logitechg.com/&matchType=prefix&filter=original:.*g333.*&filter=statuscode:200&collapse=urlkey&output=json&limit=20&fl=timestamp,original'
    rows=json.loads(get(u) or '[]')[1:]
except Exception as e: rows=[['ERR',str(e)]]
out['rows']=rows
imgs=[]
for ts,orig in [r for r in rows if r[0]!='ERR'][:6]:
    try:
        h=get(f'http://web.archive.org/web/{ts}id_/{orig}')
        imgs+=re.findall(r'/content/dam/gaming/[^"\'\s)&?]+\.(?:png|jpg)',h)
    except Exception: pass
    time.sleep(2)
out['imgs']=sorted(set(i for i in imgs if 'g333' in i))
json.dump(out,open('wb/g333.json','w'),indent=1)
PY
