python3 - <<'PY'
import urllib.request,json,re,time
def get(u,t=60):
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    return urllib.request.urlopen(req,timeout=t).read().decode('utf8','ignore')
res={}
for k,urls in {'g435':['https://www.logitechg.com/zh-cn/products/gaming-audio/g435-wireless-bluetooth-gaming-headset.981-001052.html','https://www.logitechg.com/zh-cn/products/gaming-audio/g435-wireless-bluetooth-gaming-headset.html','https://www.logitechg.com/en-us/products/gaming-audio/g435-wireless-bluetooth-gaming-headset.html','https://www.logitechg.com/en-us/products/gaming-audio/g435-wireless-bluetooth-gaming-headset.981-001049.html'],
 'g333':['https://www.logitechg.com/zh-cn/products/gaming-audio/g333-in-ear-gaming-headphones.html','https://www.logitechg.com/en-us/products/gaming-audio/g333-in-ear-gaming-headphones.html','https://www.logitechg.com/en-us/products/gaming-audio/g333-in-ear-gaming-headphones.981-000922.html']}.items():
    imgs=[]
    for u in urls:
        for ts in ['2024','2023','2022']:
            try:
                h=get(f'http://web.archive.org/web/{ts}id_/{u}')
                f=re.findall(r'/content/dam/gaming/[^"\'\s)]+\.(?:png|jpg)',h)
                if f: imgs+=f; break
            except Exception as e: pass
            time.sleep(2)
        if imgs: break
    res[k]=sorted(set(i for i in imgs if 'gallery' in i))[:60]
json.dump(res,open('wb/g435g333.json','w'),indent=1)
PY
