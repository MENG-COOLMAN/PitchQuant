import re

path = r'football-api.sql (path via env SQL_PATH)'

with open(path, 'rb') as f:
    data = f.read()

pattern = re.compile(rb"INSERT INTO `fixtures` VALUES \(")
positions = [m.start() for m in pattern.finditer(data)]
prefix_len = len(b"INSERT INTO `fixtures` VALUES (")

pos = positions[0]
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

raw = data[start:end]
print(f'Raw bytes 500-800: {raw[500:800]}')
print(f'---')
print(f'Raw bytes 800-1100: {raw[800:1100]}')
