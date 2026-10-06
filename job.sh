mkdir -p out/p2 store
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
get(){ curl -sL -A "$UA" -H "Accept-Language: zh-CN,zh;q=0.9" --compressed -m 90 -o "out/p2/$1" -w "%{http_code} %{url_effective} $1\n" "$2"; }
while read n u; do get "$n" "$u"; sleep 1; done <<'L'
zh_pro-x2-rapid.html https://www.logitechg.com/zh-cn/shop/p/pro-x2-rapid
zh_pro-x3-lightspeed.html https://www.logitechg.com/zh-cn/shop/p/pro-x3-lightspeed
zh_yeti-2.html https://www.logitechg.com/zh-cn/shop/p/yeti-2
zh_pro-x-control.html https://www.logitechg.com/zh-cn/shop/p/pro-x-control-gaming-mousepad
zh_rs50-mclaren.html https://www.logitechg.com/zh-cn/shop/p/rs50-mclaren-racing-bundle
zh_rs50-system.html https://www.logitechg.com/zh-cn/shop/p/rs50-system
zh_pro-x3-superstrike.html https://www.logitech.com/zh-cn/shop/p/pro-x3-superstrike-mouse
zh_g502-x-plus.html https://www.logitech.com/zh-cn/shop/p/g502-x-plus-wireless-lightforce
zh_g316-x-8k.html https://www.logitechg.com/zh-cn/shop/p/g316-x-8k-customizable-mechanical-gaming-keyboard
zh_g316.html https://www.logitechg.com/zh-cn/shop/p/g316-mechanical-keyboard
zh_g305-x.html https://www.logitechg.com/zh-cn/shop/p/g305-x-superlight
zh_g316-x-75.html https://www.logitechg.com/zh-cn/shop/p/g316-x-75-gaming-keyboard
zh_g316-x-98.html https://www.logitechg.com/zh-cn/shop/p/g316-x-98-gaming-keyboard
zh_keycaps.html https://www.logitechg.com/zh-cn/shop/p/g-keycaps-pbt-keycaps
zh_rs-pedals-se.html https://www.logitechg.com/zh-cn/shop/p/rs-pedals-se
zh_a50x.html https://www.logitechg.com/zh-cn/shop/p/a50-x-astro-wireless-headset
zh_zone-vibe-pro-business.html https://www.logitech.com/zh-cn/products/headsets/zone-vibe-pro-business.html
zh_zone-vibe-pro.html https://www.logitech.com/zh-cn/shop/p/zone-vibe-pro-headphones
zh_mx-master-4-business.html https://www.logitech.com/zh-cn/products/mice/mx-master-4-business.html
zh_rally-mic-pod-2.html https://www.logitech.com/zh-cn/products/video-conferencing/accessories/rally-mic-pod-2.html
zh_meetup2.html https://www.logitech.com/zh-cn/products/video-conferencing/conference-cameras/meetup2.html
zh_meetup2-shop.html https://www.logitech.com/zh-cn/shop/p/meetup2-conferencecam
zh_reach-camera.html https://www.logitech.com/zh-cn/products/education/cameras/reach-camera.html
zh_mx-anywhere-3s-business.html https://www.logitech.com/zh-cn/products/mice/mx-anywhere-3s-business-wireless-mouse.html
zh_mk950-business.html https://www.logitech.com/zh-cn/products/combos/signature-slim-mk950-business.html
zh_zone-wireless-2-business.html https://www.logitech.com/zh-cn/products/headsets/zone-wireless-2-business-headset.html
en_pro-x2-rapid.html https://www.logitechg.com/en-us/shop/p/pro-x2-rapid
en_pro-x3-lightspeed.html https://www.logitechg.com/en-us/shop/p/pro-x3-lightspeed
en_yeti-2.html https://www.logitechg.com/en-us/shop/p/yeti-2
en_pro-x-control.html https://www.logitechg.com/en-us/shop/p/pro-x-control-gaming-mousepad
en_rs50-mclaren.html https://www.logitechg.com/en-us/shop/p/rs50-mclaren-racing-bundle
en_pro-x3-superstrike.html https://www.logitechg.com/en-us/shop/p/pro-x3-superstrike-mouse
en_g305-x.html https://www.logitechg.com/en-us/shop/p/g305-x-superlight
en_g316-x-75.html https://www.logitechg.com/en-us/shop/p/g316-x-75-gaming-keyboard
en_g316-x-98.html https://www.logitechg.com/en-us/shop/p/g316-x-98-gaming-keyboard
en_keycaps.html https://www.logitechg.com/en-us/shop/p/g-keycaps-pbt-keycaps
en_rs-pedals-se.html https://www.logitechg.com/en-us/shop/p/rs-pedals-se
en_a50x.html https://www.logitechg.com/en-us/shop/p/a50-x-astro-wireless-headset
en_g502-x-plus.html https://www.logitechg.com/en-us/shop/p/g502-x-plus-wireless-lightforce
en_zone-vibe-pro-business.html https://www.logitech.com/en-us/shop/p/zone-vibe-pro-business
en_zone-vibe-pro.html https://www.logitech.com/en-us/shop/p/zone-vibe-pro-headphones
en_mx-master-4-business.html https://www.logitech.com/en-us/shop/p/mx-master-4-business
en_rally-mic-pod-2.html https://www.logitech.com/en-us/business/shop/p/rally-mic-pod-2
en_meetup2.html https://www.logitech.com/en-us/shop/p/meetup2-conferencecam
en_reach-camera.html https://www.logitech.com/en-us/products/education/cameras/reach-camera.html
L
API=https://lgshopapi.wincheers.com/api/services/app/
H=(-H "Content-Type: application/json" -H "client_id: logitech" -H "client_secret: app" -H "grant_type: password" -H "OrderSouce: 1" -H "Origin: https://store.logitech.com.cn" -H "Referer: https://store.logitech.com.cn/")
curl -s -m 90 -X POST "${H[@]}" "${API}product/GetProductList" -d '{"Sorting":"Sort","PageSize":600,"pageSize":600,"MaxResultCount":600}' > store/new_a.json
curl -s -m 90 -X POST "${H[@]}" "${API}product/GetProductList" -d '{"Sorting":"Sort","MaxResultCount":200,"SkipCount":200}' > store/new_b.json
curl -s -m 90 -X POST "${H[@]}" "${API}product/GetProductList" -d '{"Sorting":"Sort","MaxResultCount":200,"SkipCount":400}' > store/new_c.json
ls -la out/p2 store
