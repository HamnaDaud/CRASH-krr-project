"""Render real captured console output (docs/shots/*.txt) to PNG, plus the metrics chart."""
import html, json
from pathlib import Path
from playwright.sync_api import sync_playwright
import numpy as np, matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
D = Path(__file__).parent / "shots"
files = {"pytest": "pytest.txt", "app_cq02": "app_cq02.txt", "app_cq09": "app_cq09.txt", "app_refuse": "app_refuse.txt",
         "similar": "similar.txt", "predict": "predict.txt"}
with sync_playwright() as p:
    b = p.chromium.launch(executable_path="/opt/pw-browsers/chromium"); pg = b.new_page(viewport={"width": 1100, "height": 400}, device_scale_factor=2)
    for k, f in files.items():
        t = (D / f).read_text()
        if k == "similar":
            t = "\n".join(t.splitlines()[:5] + t.splitlines()[-2:]) if False else t
            ls = t.splitlines(); t = "\n".join(ls[:2]) + "\n...(JSON of 3 neighbours, see docs)...\n" + "\n".join(ls[-2:]) if False else t
        t = "\n".join(l[:170] for l in t.splitlines())
        pg.set_content(f"<body style='margin:0;background:#0f172a'><pre style='color:#e2e8f0;font:13px/1.35 monospace;padding:14px;margin:0;white-space:pre-wrap;word-break:break-all'>{html.escape(t)}</pre>")
        pg.locator("pre").screenshot(path=str(D / f"{k}.png"))
    b.close()
s = json.load(open(D.parent.parent / "results/embedding_summary_3seeds.json"))
fig, ax = plt.subplots(figsize=(6.5, 3))
ms = ["TransE", "Popularity", "Random"]; ks = ["MRR", "Hits@1", "Hits@3"]
w = 0.25
for i, m in enumerate(ms):
    ax.bar(np.arange(3) + i * w, [s[m][k][0] for k in ks], w, yerr=[s[m][k][1] for k in ks], label=m,
           color=["#2563eb", "#9ca3af", "#e5e7eb"][i], edgecolor="#374151")
ax.set_xticks(np.arange(3) + w); ax.set_xticklabels(ks); ax.set_ylim(0, 1); ax.legend(frameon=False); ax.set_ylabel("score (mean of 3 seeds)")
ax.spines[["top", "right"]].set_visible(False); plt.tight_layout(); plt.savefig(D / "metrics.png", dpi=200)
