mkdir -p wb/new
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
get(){ curl -sL -A "$UA" -H "Accept-Language: zh-CN,zh;q=0.9" --compressed -m 90 -o "wb/new/$1" -w "%{http_code} %{url_effective} $1\n" "$2"; }
get zh_sitemap.xml https://www.logitech.com/zh-cn/sitemap.xml
get zh_sitemap_biz.xml https://www.logitech.com/zh-cn/sitemap-business.xml
get en_sitemap.xml https://www.logitech.com/en-us/sitemap.xml
get en_sitemap_biz.xml https://www.logitech.com/en-us/sitemap-business.xml
get g_zh_sitemap.xml https://www.logitechg.com/zh-cn/sitemap.xml
get g_en_sitemap.xml https://www.logitechg.com/en-us/sitemap.xml
get g_robots.txt https://www.logitechg.com/robots.txt
get zh_home.html https://www.logitech.com/zh-cn
get g_zh_home.html https://www.logitechg.com/zh-cn
get zh_g_home.html https://www.logitech.com/zh-cn/logitech-g
get zh_biz_home.html https://www.logitech.com/zh-cn/business
get zh_new.html https://www.logitech.com/zh-cn/shop/c/new-arrivals
get en_new.html https://www.logitech.com/en-us/shop/c/new-arrivals
get g_play_zh.html https://www.logitechg.com/zh-cn/events/g-play.html
get g_play_en.html https://www.logitechg.com/en-us/events/g-play.html
get g_play2_zh.html https://www.logitech.com/zh-cn/logitech-g/g-play
get g_play2_en.html https://www.logitech.com/en-us/logitech-g/g-play
ls -la wb/new
