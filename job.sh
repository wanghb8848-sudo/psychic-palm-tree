python3 - <<'PY'
import urllib.request,json,re,os,time
def get(u,t=60,binary=False):
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    d=urllib.request.urlopen(req,timeout=t).read()
    return d if binary else d.decode('utf8','ignore')
prev=json.load(open('wb/cdx.json'))
kw={'mx-master-2s':['www.logitech.com/zh-cn/products/mice/','mx-master-2s'],'m188':['www.logitech.com.cn/zh-cn/products/mice/','m188'],'mk276':['www.logitech.com/','mk276'],'zone-wired':['www.logitech.com/en-us/products/headsets/','zone-wired\\.'],'h800':['www.logitech.com/zh-cn/products/headsets/','h800'],'jaybird':['www.jaybirdsport.com/','freedom'],
'g903':['www.logitechg.com/','g903'],'g604':['www.logitechg.com/','g604'],'g402':['www.logitechg.com/','g402'],'g300s':['www.logitechg.com/','g300'],'g813':['www.logitechg.com/','g813'],'g933':['www.logitechg.com/','g933'],'g533':['www.logitechg.com/','g533'],'g433':['www.logitechg.com/','g433'],'g430':['www.logitechg.com/','g430'],'g331':['www.logitechg.com/','g331'],'g233':['www.logitechg.com/','g233']}
res={}
for k,(loc,pat) in kw.items():
    rows=[]
    for attempt in range(3):
        try:
            u=f'http://web.archive.org/cdx/search/cdx?url={loc}&matchType=prefix&filter=original:.*{pat}.*&filter=statuscode:200&collapse=urlkey&output=json&limit=12&fl=timestamp,original'
            rows=json.loads(get(u) or '[]')[1:]; break
        except Exception as e: time.sleep(8)
    rows=[r for r in rows if 'zh-cn' in r[1] or 'en-us' in r[1] or 'jaybird' in r[1]] or rows
    imgs=[]
    for ts,orig in rows[:4]:
        try:
            h=get(f'http://web.archive.org/web/{ts}id_/{orig}')
            imgs+=re.findall(r'https?://[a-z.]*logitech[a-z]*\.com[^"\'\s)]*?/content/dam/[^"\'\s)]+\.(?:png|jpg)',h)
            imgs+=re.findall(r'https?://[^"\'\s)]+jaybird[^"\'\s)]+\.(?:png|jpg)',h) if k=='jaybird' else []
        except Exception as e: time.sleep(5)
        if len(imgs)>3: break
        time.sleep(2)
    seen=[];[seen.append(i) for i in imgs if i not in seen]
    res[k]=rows[:5]; res[k+'__imgs']=seen[:40]
    time.sleep(3)
prev.update(res)
json.dump(prev,open('wb/cdx.json','w'),indent=1)
PY
