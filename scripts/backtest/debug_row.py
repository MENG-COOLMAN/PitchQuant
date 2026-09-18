import csv, io, re

path = r'football-api.sql (path via env SQL_PATH)'

with open(path, 'rb') as f:
    data = f.read()

pattern = re.compile(rb"INSERT INTO `fixtures` VALUES \(")
positions = [m.start() for m in pattern.finditer(data)]
prefix_len = len(b"INSERT INTO `fixtures` VALUES (")

# Debug first 3 fixtures
for idx in range(min(3, len(positions))):
    pos = positions[idx]
    start = pos + prefix_len
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
        row = list(csv.reader(io.StringIO(vals_str), quotechar="'"))[0]
        print(f'Fixture {idx}: row len={len(row)}')
        print(f'  row[9] (status) = [{row[9]}]')
        print(f'  row[14] (league) = [{row[14]}]')
        print(f'  row[26] (gh) = [{row[26]}]')
        print(f'  row[27] (ga) = [{row[27]}]')
        for j, v in enumerate(row):
            if v.strip() == 'FT':
                print(f'  Found FT at index {j}')
    except Exception as e:
        print(f'Fixture {idx}: ERROR {e}')
        # Print raw
        print(f'  Raw first 200: {vals_str[:200]}')
        print(f'  Raw last 100: {vals_str[-100:]}')
    print()
