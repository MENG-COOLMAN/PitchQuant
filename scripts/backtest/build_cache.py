import re, csv, io, json, os

path = r'football-api.sql (path via env SQL_PATH)'
cache = 'data/fixture_cache.json'

if os.path.exists(cache):
    with open(cache, 'r') as f:
        idx = json.load(f)
    print(f'Loaded {len(idx)} from cache')
else:
    print('Building cache...')
    with open(path, 'rb') as f:
        data = f.read()
    
    pat = re.compile(rb"INSERT INTO `fixtures` VALUES \(")
    pos_list = [m.start() for m in pat.finditer(data)]
    prefix = len(b"INSERT INTO `fixtures` VALUES (")
    
    idx = []
    for pi, pos in enumerate(pos_list):
        start = pos + prefix
        depth = 0
        end = start
        for i in range(start, min(start + 3000, len(data))):
            b = data[i]
            if b == 39:
                if i+1 < len(data) and data[i+1] == 39:
                    continue
                depth = 1 - depth
            elif depth == 0 and b == 41:
                end = i
                break
        
        vals_str = data[start:end].decode('utf-8', errors='replace')
        try:
            row = list(csv.reader(io.StringIO(vals_str), quotechar="'", skipinitialspace=True))[0]
            if len(row) >= 28 and row[10] == 'FT':
                idx.append({
                    'd': row[1][:10],
                    'ln': row[14],
                    'hn': row[19],
                    'an': row[23],
                    'gh': int(row[26]) if row[26] and row[26] != 'NULL' else 0,
                    'ga': int(row[27]) if row[27] and row[27] != 'NULL' else 0
                })
        except:
            pass
        if pi % 15000 == 0:
            print(f'  {pi}/{len(pos_list)}')
    
    os.makedirs('data', exist_ok=True)
    with open(cache, 'w', encoding='utf-8') as f:
        json.dump(idx, f, ensure_ascii=False)
    print(f'Cached {len(idx)} fixtures, {os.path.getsize(cache)/1024/1024:.1f}MB')
