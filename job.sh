API=https://lgshopapi.wincheers.com/api/services/app/
H=(-H "Content-Type: application/json" -H "client_id: logitech" -H "client_secret: app" -H "grant_type: password" -H "OrderSouce: 1" -H "Origin: https://store.logitech.com.cn" -H "Referer: https://store.logitech.com.cn/")
curl -s -m 90 -X POST "${H[@]}" "${API}product/GetProductList" -d '{"Sorting":"Sort","PageSize":600,"pageSize":600,"MaxResultCount":600}' > store/all_a.json
curl -s -m 90 -X POST "${H[@]}" "${API}product/GetProductList" -d '{"Sorting":"Sort","MaxResultCount":200,"SkipCount":200}' > store/all_b.json
curl -s -m 90 -X POST "${H[@]}" "${API}product/GetProductList" -d '{"Sorting":"Sort","MaxResultCount":200,"SkipCount":400}' > store/all_c.json
ls -la store
