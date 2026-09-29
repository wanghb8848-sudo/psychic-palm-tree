API=https://lgshopapi.wincheers.com/api/services/app/
H=(-H "Content-Type: application/json" -H "client_id: logitech" -H "client_secret: app" -H "grant_type: password" -H "OrderSouce: 1" -H "Origin: https://store.logitech.com.cn" -H "Referer: https://store.logitech.com.cn/")
mkdir -p store
for u in "product/GetProductList" "Product/GetProductListPC" "Page/GetProductPageList"; do
  echo "== $u"
  curl -s -m 30 -X POST "${H[@]}" "$API$u" -d '{"PageIndex":1,"PageSize":50,"pageIndex":1,"pageSize":50}' | head -c 1500; echo
done
echo "== search"
curl -s -m 30 -X POST "${H[@]}" "${API}product/GetSelectStrAllKey?WordsKey=MX&TakeCount=5" | head -c 1500; echo
curl -s -m 30 -X GET "${H[@]}" "${API}product/GetSelectStrAllKey?WordsKey=MX&TakeCount=5" | head -c 1500; echo
