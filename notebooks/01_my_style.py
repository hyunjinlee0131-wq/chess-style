# %%
import os
import sys

sys.path.insert(0, "..")
import matplotlib.pyplot as plt
import pandas as pd

from chessstyle import features, fetch, match, profile

USERNAME = os.environ["CHESS_USERNAME"]

# %%
games = fetch.games(USERNAME)
engine = features.open_engine()
table = features.features_table(games, USERNAME, engine)
if engine:
    engine.quit()
print(len(games), "rated rapid games;", (table.who == "player").sum(), "analysed (10+ moves)")

# %% Style profile: current games vs same-rating peers
z, cur = profile.player_frame(table)
me = z[cur]
vec = me[profile.FEATURES].mean()
print(f"current games: {cur.sum()} (rating {me.rating.min()}–{me.rating.max()})")
for group, fs in profile.GROUPS.items():
    print(f"\n{group}: {vec[fs].mean():+.2f}σ")
    for f in fs:
        print(f"  {f:<20}{vec[f]:+.2f}σ{'  *both players shape this' if f in profile.INTERACTIVE else ''}")

# %% Openings and material blunders (raw, not z-scored)
mine = table[cur]
print((mine.family + " as " + mine.side).value_counts(normalize=True).head(6).round(2))
peers = table[table.game.isin(mine.game) & (table.who == "opponent")]
print(f"material blunders/game: you {mine.material_blunders.mean():.2f}, peers {peers.material_blunders.mean():.2f}")

# %% Climb: style vs same-band peers across rating bands
p = z[(z.who == "player") & z.band.notna()]
labels = table.loc[p.index].groupby(p.band).player_rating.agg(lambda r: f"{r.min()}–{r.max()}")
climb = pd.DataFrame({g: p.groupby("band")[fs].mean().mean(axis=1) for g, fs in profile.GROUPS.items()})
climb.index = labels.loc[climb.index]
climb.plot(marker="o", figsize=(9, 4), title="Style vs same-rating peers as rating climbed (σ)")
plt.axhline(0, color="grey", lw=0.5)
plt.show()

# %% GM matches with reasons and uncertainty
gm = pd.read_csv(fetch.DATA / "gm_games.csv")
P = profile.vectors(profile.normalise(gm, gm.username.notna()))
boot = match.bootstrap(me, P)
for u, r in boot.head(5).iterrows():
    e = match.explain(vec, P.loc[u])
    print(f"{u:<20} {r.sim:.2f} [{r.lo:.2f}, {r.hi:.2f}]  P(top3)={r.p_top:.0%}  "
          f"shared: {', '.join(e['shared'])}  differs: {e['differs']}")

# %% Repertoire matches and reading list
fams = (mine.family + "|" + mine.side).value_counts().head(3).index
print((gm.family + "|" + gm.side).isin(fams).groupby(gm.username).mean().nlargest(5).round(2))
for url in match.reading_list(gm, boot.index[0], fams):
    print(url)

# %% Stability: do the two halves of my current games agree?
m = me.sort_values("end_time")
half = len(m) // 2
a = match.similarities(m.iloc[:half][profile.FEATURES].mean(), P).nlargest(5).index
b = match.similarities(m.iloc[half:][profile.FEATURES].mean(), P).nlargest(5).index
print("top-5 overlap between halves:", len(set(a) & set(b)), "/ 5")
