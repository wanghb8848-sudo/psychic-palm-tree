API=https://lgshopapi.wincheers.com/api/services/app/
H=(-H "Content-Type: application/json" -H "client_id: logitech" -H "client_secret: app" -H "grant_type: password" -H "OrderSouce: 1" -H "Origin: https://store.logitech.com.cn" -H "Referer: https://store.logitech.com.cn/")
mkdir -p store/detail
for q in "?id=4575" "?Id=4575" "?productId=4575"; do echo "== GET $q"; curl -s -m 30 "${H[@]}" "${API}product/GetProductDetail$q" | head -c 3000; echo; done
echo "== POST"; curl -s -m 30 -X POST "${H[@]}" "${API}product/GetProductDetail" -d '{"id":4575,"Id":4575,"productId":4575}' | head -c 3000; echo
