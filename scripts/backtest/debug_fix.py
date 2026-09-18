import re

path = r'football-api.sql (path via env SQL_PATH)'
count = 0
with open(path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if "INSERT INTO `fixtures` VALUES" in line:
            count += 1
            if count <= 3:
                # Print with escapes visible
                print(f'Line {count}: len={len(line)}, starts with: {line[:100]}')
                # Check if ends with );
                if line.rstrip().endswith(';'):
                    print(f'  ENDS WITH ;')
                else:
                    print(f'  ENDS WITH: ...{line[-50:]}')
                # Try regex
                m = re.search(r'VALUES\s*\((.+)\);\s*$', line)
                if m:
                    print(f'  REGEX MATCH, val len={len(m.group(1))}')
                else:
                    print(f'  REGEX FAIL')
            if count >= 10:
                break
print(f'\nTotal fixture INSERT lines: {count}')
