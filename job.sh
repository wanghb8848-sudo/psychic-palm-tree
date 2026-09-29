API=https://lgshopapi.wincheers.com/api/services/app/
H=(-H "Content-Type: application/json" -H "client_id: logitech" -H "client_secret: app" -H "grant_type: password" -H "OrderSouce: 1" -H "Origin: https://store.logitech.com.cn" -H "Referer: https://store.logitech.com.cn/")
mkdir -p store
for p in 1 2 3 4 5 6; do
curl -s -m 60 -X POST "${H[@]}" "${API}product/GetProductList" -d "{\"Sorting\":\"Sort\",\"PageIndex\":$p,\"PageSize\":200,\"pageIndex\":$p,\"pageSize\":200,\"SkipCount\":$(( (p-1)*200 )),\"MaxResultCount\":200}" > store/list_$p.json
done
curl -s -m 60 -X POST "${H[@]}" "${API}Page/GetProductPageList" -d '{}' > store/pagelist.json
ls -la store
