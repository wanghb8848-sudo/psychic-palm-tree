python3 - <<'PY'
import urllib.request,json,re,os,time
kw={'m188':'m188','m380':'m380','m325s':'m325','mx-master-3':'mx-master-3[^s]','mx-master-2s':'mx-master-2s','k845':'k845','k835':'k835','mk545':'mk545','mk276':'mk276','mk200':'mk200','zone-wired':'zone-wired','zone-earbuds':'zone-wired-earbuds','h600':'h600','h800':'h800','jaybird':'jaybird-freedom','g903':'g903','g604':'g604','g402':'g402','g300s':'g300','g813':'g813','g933':'g933','g533':'g533','g433':'g433','g430':'g430','g331':'g331','g233':'g233'}
os.makedirs('wb',exist_ok=True)
res={}
def get(u,t=60):
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    return urllib.request.urlopen(req,timeout=t).read().decode('utf8','ignore')
for k,pat in kw.items():
    out=[]
    for loc in ['www.logitech.com/zh-cn/products/','www.logitech.com/en-us/products/','www.logitech.com.cn/zh-cn/products/']:
        try:
            u=f'http://web.archive.org/cdx/search/cdx?url={loc}&matchType=prefix&filter=original:.*{pat}.*&filter=statuscode:200&collapse=urlkey&output=json&limit=15&fl=timestamp,original'
            rows=json.loads(get(u) or '[]')[1:]
            out+= [r for r in rows]
        except Exception as e: out.append(['ERR',str(e)[:80]])
        time.sleep(1)
    res[k]=out
    # fetch best snapshot and extract images
    imgs=[]
    for ts,orig in [r for r in out if r[0]!='ERR'][:3]:
        try:
            h=get(f'http://web.archive.org/web/{ts}id_/{orig}')
            imgs+=re.findall(r'https?://resource\.logitech\.com[^"\'\s)]+\.(?:png|jpg)',h)
            imgs+=['https://www.logitech.com'+x for x in re.findall(r'"(/assets/\d+/[^"]+\.(?:png|jpg))"',h)]
        except Exception as e: pass
        if imgs: break
        time.sleep(1)
    seen=[];[seen.append(i) for i in imgs if i not in seen]
    res[k+'__imgs']=seen[:40]
json.dump(res,open('wb/cdx.json','w'),indent=1)
PY
