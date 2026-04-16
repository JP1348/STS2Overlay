from data.cards import CARDS
counts = {}
for k, v in CARDS.items():
    c = v.get('class', 'unknown')
    counts[c] = counts.get(c, 0) + 1
for k in sorted(counts):
    print(f'{k}: {counts[k]}')
print('TOTAL:', sum(counts.values()))
