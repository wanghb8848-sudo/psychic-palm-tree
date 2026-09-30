API=https://lgshopapi.wincheers.com/api/services/app/
mkdir -p store/detail
cat ids.txt | xargs -P 8 -I{} sh -c 'curl -s -m 40 -X POST -H "Content-Type: application/json" -H "client_id: logitech" -H "client_secret: app" -H "grant_type: password" -H "OrderSouce: 1" -H "Origin: https://store.logitech.com.cn" -H "Referer: https://store.logitech.com.cn/" "'$API'product/GetProductDetail" -d "{\"id\":{}}" > store/detail/{}.json'
ls store/detail | wc -l
