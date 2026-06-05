import json
import os

def process(file_path, out_file, cache):
    with open(file_path, 'r', encoding='utf-8') as f:
        companies = json.load(f)
        
    res = {}
    missing = []
    for c in companies:
        if c in cache:
            res[c] = cache[c]
        else:
            missing.append(c)
            
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
        
    if missing:
        print(f"Warning: {len(missing)} companies in {file_path} not found in auto_corp_cache.json")
    else:
        print(f"Successfully processed {file_path} -> {out_file}")

def main():
    with open('auto_corp_cache.json', 'r', encoding='utf-8') as f:
        cache = json.load(f)
        
    process('car_companies.json', 'car_companies_corp_code.json', cache)
    process('semi_companies.json', 'semi_companies_corp_code.json', cache)
    process('ship_companies.json', 'ship_companies_corp_code.json', cache)

if __name__ == "__main__":
    main()
