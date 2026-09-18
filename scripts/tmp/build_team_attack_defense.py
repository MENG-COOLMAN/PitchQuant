import csv, io, sys, json
from collections import defaultdict
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
team = defaultdict(lambda: [0,0,0])
with open('data/Matches.csv', encoding='utf-8-sig') as f:
    rd = csv.reader(f); hdr = next(rd)
    idx = {h: i for i, h in enumerate(hdr)}
    for r in rd:
        if len(r) < 14: continue
        try:
            gh = int(float(r[idx['FTHome']])); ga = int(float(r[idx['FTAway']]))
        except: continue
        h, a = r[idx['HomeTeam']].strip(), r[idx['AwayTeam']].strip()
        team[h][0] += gh; team[h][1] += ga; team[h][2] += 1
        team[a][0] += ga; team[a][1] += gh; team[a][2] += 1
d5 = {}
for t, (gf, ga, n) in team.items():
    if n >= 10:
        d5[t] = {'gf': round(gf/n, 2), 'ga': round(ga/n, 2), 'n': n}
with open('data/tmp/team_attack_defense.json', 'w', encoding='utf-8') as f:
    json.dump(d5, f, ensure_ascii=False, indent=1)
print('team_attack_defense.json: %d 队' % len(d5))
for t in ['Manchester City','Bayern Munich','Real Madrid','Barcelona','Paris Saint Germain','Liverpool','Atletico Madrid']:
    if t in d5: print('  %s: 进%s 失%s (n=%d)' % (t, d5[t]['gf'], d5[t]['ga'], d5[t]['n']))
