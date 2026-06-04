import requests
r = requests.get("https://www.coles.com.au/search/products?q=milk", timeout=15, headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"})
print(f"Status: {r.status_code}, Length: {len(r.text)}, NEXT_DATA: {'NEXT_DATA' in r.text}")
