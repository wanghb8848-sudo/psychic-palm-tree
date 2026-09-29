python3 - <<'PY'
import urllib.request,json,re,os,time
def get(u,t=60):
    req=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'})
    return urllib.request.urlopen(req,timeout=t).read().decode('utf8','ignore')
G='https://www.logitechg.com/%s/products/'
cands={
'g903':['gaming-mice/g903-lightspeed-wireless-mouse.html','gaming-mice/g903-hero-wireless-gaming-mouse.html'],
'g604':['gaming-mice/g604-wireless-gaming-mouse.html'],
'g402':['gaming-mice/g402-hyperion-fury-fps-gaming-mouse.html'],
'g300s':['gaming-mice/g300s-optical-ambidextrous-gaming-mouse.html'],
'g813':['gaming-keyboards/g813-rgb-mechanical-gaming-keyboard.html'],
'g933':['gaming-audio/g933-artemis-spectrum-wireless-7-1-surround-gaming-headset.html','gaming-audio/g933-wireless-7-1-lightsync-gaming-headset.html'],
'g533':['gaming-audio/g533-wireless-dts-7-1-surround-sound-gaming-headset.html','gaming-audio/g533-wireless-headset-dts-7-1-surround.html'],
'g433':['gaming-audio/g433-7-1-wired-surround-gaming-headset.html'],
'g430':['gaming-audio/g430-surround-sound-gaming-headset.html'],
'g331':['gaming-audio/g331-stereo-gaming-headset.html'],
'g233':['gaming-audio/g233-prodigy-gaming-headset.html'],
}
urls={k:[G%loc+p for p in v for loc in ('zh-cn','en-us')] for k,v in cands.items()}
urls['mx-master-2s']=['https://www.logitech.com/zh-cn/products/mice/mx-master-2s-flow.910-005141.html','https://www.logitech.com/en-us/products/mice/mx-master-2s-flow.910-005131.html','https://www.logitech.com/zh-cn/products/mice/mx-master-2s-flow.html']
urls['h800']=['https://www.logitech.com/zh-cn/products/headsets/h800-bluetooth-wireless-mic.html','https://www.logitech.com/en-us/products/headsets/h800-bluetooth-wireless-mic.981-000337.html']
urls['zone-wired']=['https://www.logitech.com/en-us/products/headsets/zone-wired.981-000871.html','https://www.logitech.com/zh-cn/products/headsets/zone-wired.html','https://www.logitech.com/en-us/products/headsets/zone-wired.html']
urls['mk276']=['https://www.logitech.com.cn/zh-cn/products/combos/mk276-wireless-keyboard-mouse.html','https://www.logitech.com/zh-cn/products/combos/mk276-wireless-keyboard-mouse.html']
urls['m188']=['https://www.logitech.com.cn/zh-cn/products/mice/m188-wireless-mouse.html','https://www.logitech.com/zh-cn/products/mice/m188-wireless-mouse.html']
res={}
for k,L in urls.items():
    imgs=[];hit=''
    for u in L:
        for ts in ['2023','2021']:
            try:
                h=get(f'http://web.archive.org/web/{ts}id_/{u}')
                f=re.findall(r'https?://[a-z.]*logitech[a-z]*\.com[^"\'\s)]*?/content/dam/[^"\'\s)]+\.(?:png|jpg)',h)
                f+=['https://www.logitechg.com'+x for x in re.findall(r'"(/content/dam/[^"]+\.(?:png|jpg))"',h)]
                f+=['https://assets.logitech.com'+x for x in re.findall(r'"(/assets/\d+/[^"]+\.(?:png|jpg))"',h)]
                if f: imgs+=f; hit=u; break
            except Exception as e: pass
            time.sleep(2)
        if imgs: break
    seen=[];[seen.append(i) for i in imgs if i not in seen]
    res[k]={'hit':hit,'imgs':seen[:40]}
    time.sleep(2)
json.dump(res,open('wb/direct.json','w'),indent=1)
PY
