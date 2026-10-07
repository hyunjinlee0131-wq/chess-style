# %%
import sys

sys.path.insert(0, "..")
import pandas as pd

from chessstyle import fetch, match, profile

gm = pd.read_csv(fetch.DATA / "gm_games.csv")
print(gm.username.nunique(), "GMs,", len(gm), "games")

# %% 1. Identification accuracy by chunk size (train = earliest 50%)
pd.DataFrame({c: match.identify(gm, chunk=c) for c in (25, 50, 100)}).T

# %% 2. Opening ablation
pd.DataFrame({"opening-adjusted": match.identify(gm, 100), "raw": match.identify(gm, 100, by_opening=False)}).T

# %% 3. Permutation importance (top-5 drop when one feature is shuffled across test games)
base = match.identify(gm, 100)["top5"]
imp = pd.Series({f: base - match.identify(gm, 100, drop=f)["top5"] for f in profile.FEATURES}).sort_values()
imp.plot.barh(figsize=(6, 7), title="Top-5 accuracy drop when feature is shuffled")

# %% 4. Sanity: shuffled GM labels must land at chance
match.identify(gm, 100, shuffle=True)

# %% Verdict against the pre-registered bar
print("PASS" if base >= 0.30 else "FAIL", f"top-5 @ 100 games = {base:.0%} (bar 30%)")

# %% 5. Blitz pool: same identification test (the app matches blitz games only against GM blitz games)
blitz = pd.read_csv(fetch.DATA / "gm_blitz.csv")
print(blitz.username.nunique(), "GMs,", len(blitz), "blitz games")
b = match.identify(blitz, 100)
print(pd.DataFrame({"blitz": b, "blitz, shuffled labels": match.identify(blitz, 100, shuffle=True)}).T)
print("PASS" if b["top5"] >= 0.30 else "FAIL", f"blitz top-5 @ 100 games = {b['top5']:.0%} (bar 30%)")

# %% 6. Same test with a time gap (each GM's middle 20% of games dropped): blitz games span months, rapid years
def gapped(t):
    t = t.sort_values("end_time", kind="stable")
    pos = t.groupby("username").cumcount() / t.groupby("username").username.transform("size")
    return t[(pos < 0.4) | (pos >= 0.6)]
span = lambda t: (t.groupby("username").end_time.agg(lambda s: s.max() - s.min()) / 86400).median()
print(f"median span per GM: rapid {span(gm):.0f} days, blitz {span(blitz):.0f} days")
pd.DataFrame({"rapid, gapped": match.identify(gapped(gm), 100), "blitz, gapped": match.identify(gapped(blitz), 100)}).T
