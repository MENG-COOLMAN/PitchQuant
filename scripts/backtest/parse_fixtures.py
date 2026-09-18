import csv, io, re

path = r'football-api.sql (path via env SQL_PATH)'
with open(path, 'rb') as f:
    data = f.read()

pattern = re.compile(rb"INSERT INTO `fixtures` VALUES \(")
positions = [m.start() for m in pattern.finditer(data)]
prefix_len = len(b"INSERT INTO `fixtures` VALUES (")

leagues = {}
total_ft = 0
errors = 0

for idx, pos in enumerate(positions):
    start = pos + prefix_len
    depth = 0
    end = start
    for i in range(start, min(start + 3000, len(data))):
        b = data[i]
        if b == 39:
            if i+1 < len(data) and data[i+1] == 39: continue
            depth = 1 - depth
        elif depth == 0 and b == 41:
            end = i
            break
    
    vals_str = data[start:end].decode('utf-8', errors='replace')
    
    try:
        row = list(csv.reader(io.StringIO(vals_str), quotechar="'", skipinitialspace=True))[0]
    except:
        errors += 1
        continue
    
    if len(row) < 28:
        errors += 1
        continue
    if row[10] != 'FT':
        continue
    
    lname = row[14]
    gh_str = row[26].strip()
    ga_str = row[27].strip()
    
    try:
        gh = int(gh_str) if gh_str and gh_str != 'NULL' else 0
        ga = int(ga_str) if ga_str and ga_str != 'NULL' else 0
    except:
        errors += 1
        continue
    
    if lname not in leagues:
        leagues[lname] = {'t': 0, 'hw': 0, 'dr': 0, 'aw': 0, 'g': 0, 'o25': 0}
    leagues[lname]['t'] += 1
    leagues[lname]['g'] += gh + ga
    if gh > ga:
        leagues[lname]['hw'] += 1
    elif gh == ga:
        leagues[lname]['dr'] += 1
    else:
        leagues[lname]['aw'] += 1
    if gh + ga > 2.5:
        leagues[lname]['o25'] += 1
    total_ft += 1
    
    if idx % 10000 == 0 and idx > 0:
        print(f'  {idx}/{len(positions)}...')

print(f'\nParsed FT: {total_ft} | Errors: {errors} | Leagues: {len(leagues)}')
print()

for k in sorted(leagues.keys(), key=lambda x: leagues[x]['t'], reverse=True)[:40]:
    d = leagues[k]
    t = d['t']
    if t >= 20:
        print(f'{k}: {t}g | H{d["hw"]/t*100:.0f}% D{d["dr"]/t*100:.0f}% A{d["aw"]/t*100:.0f}% | avg {d["g"]/t:.2f} | O2.5 {d["o25"]/t*100:.0f}%')
