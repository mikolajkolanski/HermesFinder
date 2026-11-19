"""Test regresji planera: dla kazdej tezy aplikacja ma zwrocic WSZYSTKIE oczekiwane karty
(dodatkowe karty od modelu sa tylko ostrzezeniem - model ma swobode doboru wykresow).

Uzycie (z dzialajacym backendem):
    python tests/eval_planner.py http://127.0.0.1:8000            # z modelem jezykowym
    python tests/eval_planner.py http://127.0.0.1:8000 --nollm    # same reguly
"""
import json, sys, time, urllib.request, concurrent.futures as cf
import os
C = os.path.dirname(os.path.abspath(__file__)); BASE = sys.argv[1]; NOLLM = "--nollm" in sys.argv; ONLY = [a for a in sys.argv[2:] if not a.startswith("--")]
exp = [e for e in json.load(open(f"{C}/theses_expected.json", encoding="utf-8")) if not ONLY or e["id"] in ONLY]

def analyze(item):
    body = {"thesis": item["thesis"], "options": {"context": item.get("context"), "disable_llm": NOLLM}}
    r = urllib.request.Request(BASE + "/api/analyze", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(r, timeout=300) as resp:
        return json.loads(resp.read()), time.time() - t0

def card_topic(c):
    t = c.get("topic") or ""
    if (c.get("dataset_id") or "").startswith("planet_"): t = c["dataset_id"]
    return t

def check(item, data):
    cards = [c for c in data["cards"]]
    errs = [c for c in cards if c.get("error")]
    good = [c for c in cards if not c.get("error")]
    problems, warnings = [], []
    for c in errs: problems.append(f"karta z błędem: {c['title']} — {c['error'][:80]}")
    allowed = {r["topic"] for r in item["require"]} | {o["topic"] for o in item.get("optional", [])}
    for c in good:
        if card_topic(c) not in allowed:
            warnings.append(f"dodatkowa karta: {card_topic(c)} ({c['title']})")
    for req in item["require"]:
        cand = [c for c in good if card_topic(c) == req["topic"]]
        if "months" in req:
            want = None if req["months"] is None else sorted(req["months"])
            cand = [c for c in cand if (sorted(c.get("months") or []) or None) == want]
        if not cand:
            problems.append(f"BRAK: {req['topic']} {req.get('regions','')} {('miesiące ' + str(req['months'])) if 'months' in req else ''}")
            continue
        if req.get("regions") is not None:
            have = set().union(*[set(c.get("region_ids") or []) for c in cand])
            miss = set(req["regions"]) - have
            if req["regions"] == [] and have: problems.append(f"ZBĘDNY REGION w {req['topic']}: {sorted(have)}")
            if miss: problems.append(f"ZŁY REGION w {req['topic']}: brak {sorted(miss)}, jest {sorted(have)}")
    mx = item.get("max_cards", len(item["require"]) + len(item.get("optional", [])))
    if len(good) > mx: warnings.append(f"więcej kart niż minimum: {len(good)} > {mx}")
    return problems, warnings

ok = 0
with cf.ThreadPoolExecutor(2) as ex:
    futs = {ex.submit(analyze, it): it for it in exp}
    results = {}
    for f in cf.as_completed(futs):
        results[futs[f]["id"]] = f.result()
for it in exp:
    data, dt = results[it["id"]]
    p, w = check(it, data)
    ok += not p
    pl = data["planner"]
    print(f"{'OK  ' if not p else 'FAIL'} {it['id']:15} {dt:5.1f}s LLM={pl.get('used')} {pl.get('model') or ''} {pl.get('llm_error') or ''}")
    for c in data["cards"]:
        print(f"       · {card_topic(c):24} reg={c.get('region_ids')} mies={c.get('months')} {'[BŁĄD]' if c.get('error') else ''} {c['title'][:60]}")
    for x in p: print("       !", x)
    for x in w: print("       ~", x)
print(f"\nWYNIK: {ok}/{len(exp)} tez z dokładnie oczekiwanymi danymi")
