#!/usr/bin/env python3
"""
Render TikZ figure templates from measured JSON outputs.
This removes manual numeric edits in paper figures.
"""

import json
from pathlib import Path

RESULTS = Path(__file__).resolve().parent / "results"


def resolve_workspace_root() -> Path:
    try:
        return Path(__file__).resolve().parents[4]
    except IndexError:
        return Path("/pipeline")


def resolve_figures_dir(root: Path) -> Path:
    for pattern in ("*Paper 2*", "*paper2*", "paper2-manuscript"):
        matches = sorted(path for path in root.glob(pattern) if (path / "figures").exists())
        if matches:
            return matches[0] / "figures"
    return RESULTS / "rendered_figures"


ROOT = resolve_workspace_root()
FIGS = resolve_figures_dir(ROOT)
FIGS.mkdir(parents=True, exist_ok=True)


def cdf_points(values, step=0.01):
    xs = [round(i * step, 2) for i in range(int(1 / step) + 1)]
    n = len(values) or 1
    ys = []
    for x in xs:
        ys.append(sum(1 for v in values if v <= x) / n)
    return xs, ys


def fmt(v):
    if isinstance(v, float):
        return f"{v:.1f}".rstrip("0").rstrip(".")
    return str(v)


def coord(v):
    return f"{v:.2f}"


def render_coverage(d):
    c = d["coverage_chart"]
    e, m, i, cap, f = c["enterprise"], c["mobile"], c["ics"], c["capec"], c["fight"]
    e_n = e.get("attack_pattern_n", 0)
    m_n = m.get("attack_pattern_n", 0)
    i_n = i.get("attack_pattern_n", 0)
    cap_n = cap.get("attack_pattern_n", 0)
    f_n = f.get("attack_pattern_n", 0)
    return f"""\\definecolor{{acmBlue}}{{HTML}}{{1F77B4}}
\\definecolor{{acmTeal}}{{HTML}}{{009E73}}
\\definecolor{{acmSand}}{{HTML}}{{D55E00}}
\\definecolor{{acmGrid}}{{HTML}}{{D9DDE2}}
\\begin{{tikzpicture}}[x=0.48cm,y=0.03cm,font=\\footnotesize]
  \\draw[->] (0,0) -- (17.2,0) node[right] {{Corpus}};
  \\draw[->] (0,0) -- (0,124) node[above] {{\\%}};
  \\foreach \\yy in {{0,20,40,60,80,100}} {{
    \\draw[acmGrid] (0,\\yy) -- (16.8,\\yy);
    \\node[left] at (0,\\yy) {{\\yy}};
  }}
  \\fill[acmBlue]   (1.0,0) rectangle (1.8,{e['platform']});
  \\fill[acmTeal]   (1.9,0) rectangle (2.7,{e['software_link']});
  \\fill[acmSand]   (2.8,0) rectangle (3.6,{e['cve_link']});
  \\node[above] at (1.4,{e['platform']}) {{{fmt(e['platform'])}}};
  \\node[above] at (2.3,{e['software_link']}) {{{fmt(e['software_link'])}}};
  \\node[above] at (3.2,{coord(max(1.7, e['cve_link'] + 0.4))}) {{{fmt(e['cve_link'])}}};
  \\fill[acmBlue]   (4.0,0) rectangle (4.8,{m['platform']});
  \\fill[acmTeal]   (4.9,0) rectangle (5.7,{m['software_link']});
  \\fill[acmSand]   (5.8,0) rectangle (6.6,{m['cve_link']});
  \\node[above] at (4.4,{m['platform']}) {{{fmt(m['platform'])}}};
  \\node[above] at (5.3,{m['software_link']}) {{{fmt(m['software_link'])}}};
  \\fill[acmBlue]   (7.0,0) rectangle (7.8,{i['platform']});
  \\fill[acmTeal]   (7.9,0) rectangle (8.7,{i['software_link']});
  \\fill[acmSand]   (8.8,0) rectangle (9.6,{i['cve_link']});
  \\node[above] at (7.4,{i['platform']}) {{{fmt(i['platform'])}}};
  \\node[above] at (8.3,{i['software_link']}) {{{fmt(i['software_link'])}}};
  \\node[above] at (9.2,{coord(max(1.7, i['cve_link'] + 0.4))}) {{{fmt(i['cve_link'])}}};
  \\fill[acmBlue!40]   (10.0,0) rectangle (10.8,{cap['platform']});
  \\fill[acmTeal!40]   (10.9,0) rectangle (11.7,{cap['software_link']});
  \\fill[acmSand!40]   (11.8,0) rectangle (12.6,{cap['cve_link']});
  \\node[above,text=gray] at (11.3,2) {{{fmt(cap['platform'])}}};
  \\fill[acmBlue]   (13.0,0) rectangle (13.8,{f['platform']});
  \\fill[acmTeal]   (13.9,0) rectangle (14.7,{f['software_link']});
  \\fill[acmSand]   (14.8,0) rectangle (15.6,{f['cve_link']});
  \\node[above] at (13.4,{f['platform']}) {{{fmt(f['platform'])}}};
  \\node[above] at (14.3,{f['software_link']}) {{{fmt(f['software_link'])}}};
  \\node[above] at (15.2,{coord(max(1.7, f['cve_link'] + 0.4))}) {{{fmt(f['cve_link'])}}};
  \\node at (2.3,-8) {{Enterprise}};
  \\node at (5.3,-8) {{Mobile}};
  \\node at (8.3,-8) {{ICS}};
  \\node at (11.3,-8) {{CAPEC}};
  \\node at (14.3,-8) {{FiGHT}};
  \\node[below,font=\\scriptsize,text=gray] at (2.3,-12) {{$n={e_n}$}};
  \\node[below,font=\\scriptsize,text=gray] at (5.3,-12) {{$n={m_n}$}};
  \\node[below,font=\\scriptsize,text=gray] at (8.3,-12) {{$n={i_n}$}};
  \\node[below,font=\\scriptsize,text=gray] at (11.3,-12) {{$n={cap_n}$}};
  \\node[below,font=\\scriptsize,text=gray] at (14.3,-12) {{$n={f_n}$}};
  \\node[anchor=north east,fill=white,fill opacity=0.95,text opacity=1,inner sep=2.2pt] at (16.5,118.0) {{
    \\begin{{tabular}}{{@{{}}l@{{}}}}
      \\textcolor{{acmBlue}}{{\\rule{{0.95em}}{{0.72em}}}}\\ \\ $\\rho_P$: platform\\\\[1pt]
      \\textcolor{{acmTeal}}{{\\rule{{0.95em}}{{0.72em}}}}\\ \\ $\\rho_S$: software\\\\[1pt]
      \\textcolor{{acmSand}}{{\\rule{{0.95em}}{{0.72em}}}}\\ \\ $\\rho_V$: CVE
    \\end{{tabular}}
  }};
\\end{{tikzpicture}}
"""


def render_software_specificity(d):
    s = d["software_specificity"]
    # Enrichment data from description-based version extraction
    enriched_total_pct = s.get("enriched_total_pct", s.get("version_no_cpe_pct", 0))
    enriched_no_version_pct = s.get("enriched_no_version_pct", s.get("no_version_no_cpe_pct", 0))
    gain_pp = s.get("gain_pp", 0)
    desc_enriched_count = s.get("desc_enriched_count", 0)
    enriched_total = s.get("enriched_total", s.get("version_no_cpe", 0))
    baseline_version_pct = s.get("version_no_cpe_pct", 0)

    return f"""\\definecolor{{acmGrayFill}}{{HTML}}{{B7BDC5}}
\\definecolor{{acmTeal}}{{HTML}}{{009E73}}
\\definecolor{{acmBlue}}{{HTML}}{{1F77B4}}
\\definecolor{{acmSand}}{{HTML}}{{D55E00}}
\\definecolor{{acmGrid}}{{HTML}}{{D9DDE2}}
\\definecolor{{acmGray}}{{HTML}}{{8A8F99}}
\\begin{{tikzpicture}}[x=0.074cm,y=1.0cm,font=\\footnotesize]
  \\draw[->] (0,0) -- (112,0) node[right] {{\\% of software objects ($N={s['total_software']}$)}};
  \\foreach \\x in {{0,20,40,60,80,100}} {{
    \\draw[acmGrid] (\\x,0) -- (\\x,3.8);
    \\node[below] at (\\x,0) {{\\x}};
  }}
  % Row 1: Structured fields only (baseline)
  \\fill[acmGrayFill] (0,2.5) rectangle ({s['no_version_no_cpe_pct']},3.1);
  \\fill[acmTeal] ({s['no_version_no_cpe_pct']},2.5) rectangle (100,3.1);
  \\node[anchor=east] at (-1.0,2.8) {{Structured}};
  \\node at ({s['no_version_no_cpe_pct']/2:.2f},2.8) {{{fmt(s['no_version_no_cpe_pct'])}\\%}};
  \\node[anchor=west,font=\\scriptsize] at (100.5,2.8) {{{fmt(baseline_version_pct)}\\% ({s['version_no_cpe']})}};
  % Row 2: With description enrichment
  \\fill[acmGrayFill] (0,1.4) rectangle ({enriched_no_version_pct},2.0);
  \\fill[acmTeal] ({enriched_no_version_pct},1.4) rectangle ({enriched_no_version_pct + baseline_version_pct},2.0);
  \\fill[acmSand] ({enriched_no_version_pct + baseline_version_pct},1.4) rectangle (100,2.0);
  \\node[anchor=east] at (-1.0,1.7) {{+Description}};
  \\node at ({enriched_no_version_pct/2:.2f},1.7) {{{fmt(enriched_no_version_pct)}\\%}};
  \\node[anchor=west,font=\\scriptsize] at (100.5,1.7) {{{fmt(enriched_total_pct)}\\% ({enriched_total})}};
  % Gain annotation
  \\draw[<->,acmSand,line width=0.7pt] (102.5,2.5) -- (102.5,2.0);
  \\node[anchor=west,font=\\scriptsize,text=acmSand] at (103.5,2.25) {{+{gain_pp}\\,pp (+{desc_enriched_count})}};
  % Legend
  \\node[anchor=north west,fill=white,fill opacity=0.95,text opacity=1,inner sep=2.2pt] at (42.0,3.7) {{
    \\begin{{tabular}}{{@{{}}l@{{}}}}
      \\textcolor{{acmGrayFill}}{{\\rule{{0.95em}}{{0.72em}}}}\\ \\ No version signal\\\\[1pt]
      \\textcolor{{acmTeal}}{{\\rule{{0.95em}}{{0.72em}}}}\\ \\ Structured version\\\\[1pt]
      \\textcolor{{acmSand}}{{\\rule{{0.95em}}{{0.72em}}}}\\ \\ Description-enriched\\\\[1pt]
      \\textcolor{{acmBlue}}{{\\rule{{0.95em}}{{0.72em}}}}\\ \\ CPE (0 objects)
    \\end{{tabular}}
  }};
\\end{{tikzpicture}}
"""


def render_tier_collapse(d):
    t = d["campaign_tier_collapse"]
    total = t["total_campaigns"]
    t1 = t["t1_count"]
    t2 = t["t2_count"]
    t3 = t["t3_count"]
    t1p = t["t1_pct"]
    t2p = t["t2_pct"]
    t3p = t["t3_pct"]
    return f"""\\definecolor{{acmBlue}}{{HTML}}{{1F77B4}}
\\definecolor{{acmTeal}}{{HTML}}{{009E73}}
\\definecolor{{acmSand}}{{HTML}}{{D55E00}}
\\definecolor{{acmGrid}}{{HTML}}{{D9DDE2}}
\\definecolor{{acmGray}}{{HTML}}{{8A8F99}}
\\begin{{tikzpicture}}[x=1.80cm,y=0.040cm,font=\\footnotesize]
  \\draw[->] (0,0) -- (4.65,0) node[right] {{Profile tier}};
  \\draw[->] (0,0) -- (0,106) node[above] {{\\% of campaigns}};
  \\foreach \\yy in {{0,20,40,60,80,100}} {{
    \\draw[acmGrid] (0,\\yy) -- (4.45,\\yy);
    \\node[left] at (0,\\yy) {{\\yy}};
  }}

  \\fill[acmBlue] (0.62,0) rectangle (1.38,{t1p});
  \\fill[acmTeal] (1.97,0) rectangle (2.73,{t2p});
  \\fill[acmSand] (3.32,0) rectangle (4.08,{t3p});

  \\node[below] at (1.00,0) {{Coarse}};
  \\node[below] at (2.35,0) {{Anchored}};
  \\node[below] at (3.70,0) {{Exploit-pinned}};

  \\node[below,font=\\footnotesize,text=acmGray] at (1.00,-7.0) {{software+platform}};
  \\node[below,font=\\footnotesize,text=acmGray] at (2.35,-7.0) {{+version/CPE or CVE}};
  \\node[below,font=\\footnotesize,text=acmGray] at (3.70,-7.0) {{+campaign CVE}};

  \\node[above,align=center] at (1.00,{t1p + 2.0:.1f}) {{\\shortstack{{{t1} campaigns\\\\({fmt(t1p)}\\%)}}}};
  \\node[above,align=center] at (2.35,{t2p + 2.0:.1f}) {{\\shortstack{{{t2} campaigns\\\\({fmt(t2p)}\\%)}}}};
  \\node[above,align=center] at (3.70,{t3p + 2.0:.1f}) {{\\shortstack{{{t3} campaigns\\\\({fmt(t3p)}\\%)}}}};

  \\node[below,font=\\footnotesize,text=acmGray] at (2.35,-12.0) {{$N={total}$ campaigns}};
\\end{{tikzpicture}}
"""


def render_cve_location(d):
    c = d["cve_location"]
    f = d.get("cve_operational_funnel", {})
    detected = f.get("detected_unique_cves", c["total"])
    actionable = f.get("actionable_cves", 0)
    campaign_linked = f.get("campaign_linked_cves", 0)
    campaigns_with_cve = f.get("campaigns_with_cve", 0)
    total_campaigns = f.get("total_campaigns", 0)
    actionable_pct = round(100 * actionable / detected, 1) if detected else 0
    linked_pct = round(100 * campaign_linked / actionable, 1) if actionable else 0
    campaign_pct = round(100 * campaigns_with_cve / total_campaigns, 1) if total_campaigns else 0
    return f"""\\definecolor{{acmBlue}}{{HTML}}{{1F77B4}}
\\definecolor{{acmTeal}}{{HTML}}{{009E73}}
\\definecolor{{acmSand}}{{HTML}}{{D55E00}}
\\definecolor{{acmGray}}{{HTML}}{{8A8F99}}
\\definecolor{{acmGrid}}{{HTML}}{{D9DDE2}}
\\begin{{tikzpicture}}[x=0.253cm,y=0.62cm,font=\\footnotesize]
  \\draw[->] (0,0) -- (33.0,0) node[right] {{Count}};
  \\foreach \\x in {{0,5,10,15,20,25,30}} {{
    \\draw[acmGrid] (\\x,0) -- (\\x,10.8);
    \\node[below] at (\\x,0) {{\\x}};
  }}
  \\node[anchor=east] at (-0.6,9.6) {{Detected CVEs}};
  \\node[anchor=east] at (-0.6,7.1) {{Actionable CVEs}};
  \\node[anchor=east] at (-0.6,4.6) {{Campaign-linked CVEs}};
  \\node[anchor=east] at (-0.6,2.1) {{Campaigns with $\\geq$1 CVE}};
  \\fill[acmBlue] (0,9.1) rectangle ({detected},10.1);
  \\fill[acmTeal] (0,6.6) rectangle ({actionable},7.6);
  \\fill[acmSand] (0,4.1) rectangle ({campaign_linked},5.1);
  \\fill[acmGray] (0,1.6) rectangle ({campaigns_with_cve},2.6);
  \\draw[densely dashed,acmGrid] (0,3.35) -- (30.8,3.35);
  \\node[anchor=west,font=\\scriptsize,text=acmGray] at (20.2,3.55) {{CVE-evidence units}};
  \\node[anchor=west,font=\\scriptsize,text=acmGray] at (20.2,0.95) {{Campaign units}};
  \\node[anchor=west] at ({detected + 0.5},9.6) {{{detected} (100\\%)}};
  \\node[anchor=west] at ({actionable + 0.5},7.1) {{{actionable} ({actionable_pct}\\% of detected)}};
  \\node[anchor=west] at ({campaign_linked + 0.5},4.6) {{{campaign_linked} ({linked_pct}\\% of actionable)}};
  \\node[anchor=west] at ({campaigns_with_cve + 0.5},2.1) {{{campaigns_with_cve} campaigns ({campaign_pct}\\% of {total_campaigns})}};
\\end{{tikzpicture}}
"""


def render_jaccard(d):
    j = d["jaccard_cdf"]
    n_is = len(j["software_only_distances"])
    xs, ys_sw = cdf_points(j["software_only_distances"])
    _, ys_sc = cdf_points(j["software_cve_distances"])
    pts_sw = " -- ".join(f"({x:.2f},{y:.3f})" for x, y in zip(xs, ys_sw))
    pts_sc = " -- ".join(f"({x:.2f},{y:.3f})" for x, y in zip(xs, ys_sc))
    confused = next((y for x, y in zip(xs, ys_sc) if abs(x - j["delta_threshold"]) < 1e-9), 0.0)
    return f"""\\definecolor{{acmBlue}}{{HTML}}{{1F77B4}}
\\definecolor{{acmTeal}}{{HTML}}{{009E73}}
\\definecolor{{acmGrid}}{{HTML}}{{D9DDE2}}
\\definecolor{{acmGray}}{{HTML}}{{8A8F99}}
\\begin{{tikzpicture}}[x=7.94cm,y=4.7cm,font=\\footnotesize]
  \\draw[->] (0,0) -- (1.05,0) node[right] {{Nearest-neighbor Jaccard distance}};
  \\draw[->] (0,0) -- (0,1.05) node[above] {{Cumulative fraction of groups}};
  \\foreach \\x in {{0,0.2,0.4,0.6,0.8,1.0}} {{
    \\draw[acmGrid] (\\x,0) -- (\\x,1.0);
    \\node[below] at (\\x,0) {{\\x}};
  }}
  \\foreach \\y in {{0,0.2,0.4,0.6,0.8,1.0}} {{
    \\draw[acmGrid] (0,\\y) -- (1.0,\\y);
    \\node[left] at (0,\\y) {{\\y}};
  }}
  \\draw[line width=0.9pt,acmBlue] {pts_sw};
  \\draw[line width=0.9pt,acmTeal,densely dashed] {pts_sc};
  \\draw[densely dashed,acmGray] ({j['delta_threshold']},0) -- ({j['delta_threshold']},1.0);
  \\node[anchor=south west,text=acmGray] at ({j['delta_threshold'] + 0.005:.3f},0.10) {{$\\delta={j['delta_threshold']}$}};
  \\node[anchor=north west,text=acmGray] at ({j['delta_threshold'] + 0.005:.3f},0.085) {{{round(100*confused,1)}\\% confused}};
  \\node[anchor=north west,fill=white,fill opacity=0.95,text opacity=1,inner sep=2.2pt] at (0.56,0.98) {{
    \\begin{{tabular}}{{@{{}}l@{{}}}}
      \\textcolor{{acmBlue}}{{\\rule{{0.95em}}{{0.72em}}}}\\ \\ Software only\\\\[1pt]
      \\textcolor{{acmTeal}}{{\\rule{{0.95em}}{{0.72em}}}}\\ \\ Software + CVE
    \\end{{tabular}}
  }};
  \\node[font=\\scriptsize,text=acmGray] at (0.5,-0.08) {{$n={n_is}$ intrusion sets, $\\delta={j['delta_threshold']}$}};
\\end{{tikzpicture}}
"""


def render_ablation(d):
    t = d["threshold_confusion"]
    vals = [
        t["baseline_all_is_confusion_pct"],
        t["confusion_pct"][0],
        t["confusion_pct"][1],
        t["confusion_pct"][2],
    ]
    samples = [
        t["baseline_all_is_sample_size"],
        t["sample_sizes"][0],
        t["sample_sizes"][1],
        t["sample_sizes"][2],
    ]
    labels = ["All IS", "k$\\geq$1", "k$\\geq$2", "k$\\geq$3"]
    colors = ["acmGray", "acmBlue", "acmTeal", "acmGold"]
    x_centers = [0.8, 1.9, 3.0, 4.1]
    points = []
    point_block = []
    for x, label, val, n, color in zip(x_centers, labels, vals, samples, colors):
        points.append(f"({x:.2f},{val:.2f})")
        label_y = val + 0.30
        point_block.append(f"  \\fill[{color}] ({x:.2f},{val:.2f}) circle (0.085);")
        point_block.append(f"  \\node[above] at ({x:.2f},{label_y:.2f}) {{{fmt(val)}\\%}};")
        point_block.append(f"  \\node[below] at ({x:.2f},0) {{{label}}};")
        point_block.append(f"  \\node[below,font=\\footnotesize,text=acmGray] at ({x:.2f},-0.9) {{n={n}}};")
    line_path = " -- ".join(points)
    point_block_text = "\n".join(point_block)
    return f"""\\definecolor{{acmBlue}}{{HTML}}{{1F77B4}}
\\definecolor{{acmTeal}}{{HTML}}{{009E73}}
\\definecolor{{acmGray}}{{HTML}}{{8A8F99}}
\\definecolor{{acmGold}}{{HTML}}{{B8860B}}
\\definecolor{{acmGrid}}{{HTML}}{{D9DDE2}}
\\begin{{tikzpicture}}[x=1.67cm,y=0.52cm,font=\\footnotesize]
  \\draw[->] (0,0) -- (5.0,0) node[right] {{Minimum evidence threshold}};
  \\draw[->] (0,0) -- (0,10.8) node[above] {{Confusion rate (\\%)}};
  \\foreach \\y in {{0,2,4,6,8,10}} {{
    \\draw[acmGrid] (0,\\y) -- (4.8,\\y);
    \\node[left] at (0,\\y) {{\\y}};
  }}
  \\draw[line width=1.0pt,acmBlue] {line_path};
{point_block_text}
\\end{{tikzpicture}}
"""


def render_compatibility_distribution(d):
    c = d["compatibility_table"]
    cf, vmr, ident = c["cf"], c["vmr"], c["id"]
    total = max(1, c.get("total", cf + vmr + ident))

    def pct(v):
        return round(100.0 * v / total, 1)

    cf_pct = c.get("cf_pct", pct(cf))
    vmr_pct = c.get("vmr_pct", pct(vmr))
    id_pct = c.get("id_pct", pct(ident))
    floor_pct = c.get("non_cf_floor_pct", 0.0)
    ceiling_pct = c.get("non_cf_ceiling_pct", 0.0)
    resolved_pct = c.get("non_cf_resolved_pct", 0.0)
    rule_coverage_pct = c.get("rule_coverage_pct", 0.0)

    return f"""\\definecolor{{acmBlue}}{{HTML}}{{1F77B4}}
\\definecolor{{acmTeal}}{{HTML}}{{009E73}}
\\definecolor{{acmSand}}{{HTML}}{{D55E00}}
\\definecolor{{acmGray}}{{HTML}}{{8A8F99}}
\\definecolor{{acmGrid}}{{HTML}}{{D9DDE2}}
\\begin{{tikzpicture}}[x=0.603cm,y=0.055cm,font=\\footnotesize]
  \\draw[->] (0,0) -- (13.8,0) node[right] {{Compatibility class / sensitivity}};
  \\draw[->] (0,0) -- (0,106) node[above] {{\\% of techniques}};
  \\foreach \\yy in {{0,20,40,60,80,100}} {{
    \\draw[acmGrid] (0,\\yy) -- (13.2,\\yy);
    \\node[left] at (0,\\yy) {{\\yy}};
  }}
  \\fill[acmBlue] (1.2,0) rectangle (2.7,{cf_pct});
  \\fill[acmTeal] (3.6,0) rectangle (5.1,{vmr_pct});
  \\fill[acmSand] (6.0,0) rectangle (7.5,{id_pct});
  \\node[above] at (1.95,{max(cf_pct, 0.5)}) {{{fmt(cf_pct)}\\%}};
  \\node[above] at (4.35,{vmr_pct}) {{{fmt(vmr_pct)}\\%}};
  \\node[above] at (6.75,{id_pct}) {{{fmt(id_pct)}\\%}};
  \\node[below] at (1.95,0) {{CF}};
  \\node[below] at (4.35,0) {{VMR}};
  \\node[below] at (6.75,0) {{ID}};
  \\node[below,font=\\scriptsize,text=gray] at (1.95,-7.0) {{{cf} techniques}};
  \\node[below,font=\\scriptsize,text=gray] at (4.35,-7.0) {{{vmr} techniques}};
  \\node[below,font=\\scriptsize,text=gray] at (6.75,-7.0) {{{ident} techniques}};
  \\draw[line width=1.1pt,acmGray] (11.0,{floor_pct}) -- (11.0,{ceiling_pct});
  \\fill[acmGray] (11.0,{floor_pct}) circle (0.085);
  \\fill[acmGray] (11.0,{ceiling_pct}) circle (0.085);
  \\fill[acmBlue] (11.0,{resolved_pct}) circle (0.085);
  \\node[anchor=west,font=\\scriptsize,text=acmGray] at (11.18,{ceiling_pct}) {{ceiling {fmt(ceiling_pct)}\\%}};
  \\node[anchor=west,font=\\scriptsize,text=acmGray] at (11.18,{floor_pct}) {{floor {fmt(floor_pct)}\\%}};
  \\node[anchor=west,font=\\scriptsize,text=acmBlue] at (11.18,{resolved_pct}) {{resolved {fmt(resolved_pct)}\\%}};
  \\node[below] at (11.0,0) {{non-CF range}};
  \\node[below,font=\\scriptsize,text=gray] at (11.0,-7.0) {{rule coverage {fmt(rule_coverage_pct)}\\%}};
  \\node[below,font=\\scriptsize,text=gray] at (6.6,-12.5) {{$N={total}$ techniques}};
\\end{{tikzpicture}}
"""


def render_compatibility_by_tactic(d):
    rows = d.get("compatibility_by_tactic", [])
    if not rows:
        return (
            "\\begin{tikzpicture}[font=\\footnotesize]\n"
            "  \\node {No compatibility-by-tactic data};\n"
            "\\end{tikzpicture}\n"
        )

    def short_label(tactic):
        mapping = {
            "command-and-control": "C2",
            "privilege-escalation": "priv-esc",
            "resource-development": "resource-dev",
            "lateral-movement": "lateral-mvmt",
            "credential-access": "cred-access",
        }
        return mapping.get(tactic, tactic)

    n = len(rows)
    y_top = n + 0.8
    y_axis = 0.2
    lines = [
        "\\definecolor{acmTeal}{HTML}{009E73}",
        "\\definecolor{acmGray}{HTML}{8A8F99}",
        "\\definecolor{acmGrid}{HTML}{D9DDE2}",
        "\\begin{tikzpicture}[x=0.079cm,y=0.52cm,font=\\footnotesize]",
        f"  \\draw[->] (0,{y_axis:.1f}) -- (106,{y_axis:.1f}) node[right] {{non-CF share (\\%)}};",
        f"  \\draw[->] (0,{y_axis:.1f}) -- (0,{y_top + 0.2:.1f});",
    ]
    for x in [0, 20, 40, 60, 80, 100]:
        lines.append(f"  \\draw[acmGrid] ({x},{y_axis:.1f}) -- ({x},{y_top:.1f});")
        lines.append(f"  \\node[below] at ({x},{y_axis:.1f}) {{{x}}};")

    for idx, row in enumerate(rows):
        y = n - idx
        non_cf = float(row.get("non_cf_pct", 0))
        total = int(row.get("total", 0))
        label = short_label(str(row.get("tactic", "")))
        lines.append(f"  \\fill[acmGray!25] (0,{y-0.28:.2f}) rectangle (100,{y+0.28:.2f});")
        lines.append(f"  \\fill[acmTeal] (0,{y-0.28:.2f}) rectangle ({non_cf:.1f},{y+0.28:.2f});")
        lines.append(f"  \\node[anchor=east] at (-1.2,{y:.2f}) {{{label}}};")
        lines.append(
            f"  \\node[anchor=west] at ({min(non_cf + 1.0, 101.0):.1f},{y:.2f}) "
            f"{{{fmt(non_cf)}\\% (n={total})}};"
        )

    lines.append(
        "  \\node[anchor=west,font=\\scriptsize,text=acmGray] at (0.0,-0.55)"
        " {Sorted by tactic support (multi-tactic techniques counted per tactic).};"
    )
    lines.append("\\end{tikzpicture}")
    lines.append("")
    return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# New figures: inNervoso consolidation
# ──────────────────────────────────────────────────────────────

TACTIC_SHORT = {
    "reconnaissance": "Recon",
    "resource-development": "Res.Dev",
    "initial-access": "Init.Acc",
    "execution": "Exec",
    "persistence": "Persist",
    "privilege-escalation": "Priv.Esc",
    "defense-evasion": "Def.Eva",
    "credential-access": "Cred.Acc",
    "discovery": "Disc",
    "lateral-movement": "Lat.Mov",
    "collection": "Collect",
    "command-and-control": "C2",
    "exfiltration": "Exfil",
    "impact": "Impact",
}


def render_tactic_coverage_heatmap(d):
    """Campaign × tactic heatmap — rows=campaigns, cols=14 tactics."""
    data = d.get('campaign_tactic_coverage', {})
    campaigns = data.get('campaigns', [])
    tactic_order = data.get('tactic_order', [])

    if not campaigns or not tactic_order:
        return "% No tactic coverage data available\n"

    # Sort campaigns by tactic_count descending for visual clarity
    campaigns = sorted(campaigns, key=lambda c: -c.get('tactic_count', 0))

    n_camps = len(campaigns)
    n_tactics = len(tactic_order)

    # Cell dimensions
    cell_w = 0.55  # cm per tactic column
    cell_h = 0.18  # cm per campaign row

    lines = [
        "\\definecolor{acmBlue}{HTML}{1F77B4}",
        "\\definecolor{acmGray}{HTML}{A0A0A0}",
        "\\definecolor{hmPresent}{HTML}{1F77B4}",
        "\\definecolor{hmAbsent}{HTML}{F0F0F0}",
        f"\\begin{{tikzpicture}}[x={cell_w}cm,y={cell_h}cm,font=\\tiny]",
    ]

    # Column headers (tactic names)
    for j, tactic in enumerate(tactic_order):
        label = TACTIC_SHORT.get(tactic, tactic[:6])
        lines.append(
            f"  \\node[rotate=60,anchor=south west] at ({j + 0.5},{n_camps + 0.3}) "
            f"{{\\textsf{{{label}}}}};"
        )

    # Grid cells
    for i, camp in enumerate(campaigns):
        y = n_camps - 1 - i
        tactics = camp.get('tactics', {})
        # Campaign label (truncated)
        name = camp.get('name', '')[:18]
        lines.append(f"  \\node[anchor=east,font=\\tiny] at (-0.2,{y + 0.5}) {{{name}}};")

        for j, tactic in enumerate(tactic_order):
            present = tactics.get(tactic, 0)
            color = "hmPresent" if present else "hmAbsent"
            lines.append(
                f"  \\fill[{color}] ({j},{y}) rectangle ({j + 1},{y + 1});"
            )

    # Border
    lines.append(f"  \\draw (0,0) rectangle ({n_tactics},{n_camps});")

    # Annotation
    lines.append(
        f"  \\node[anchor=west,font=\\scriptsize] at (0,-1.0) "
        f"{{$N={n_camps}$ campaigns, sorted by tactic coverage.}};"
    )

    lines.append("\\end{tikzpicture}")
    lines.append("")
    return "\n".join(lines)


def render_ieir_breakdown(d):
    """IEIR stacked bar — campaign-specific vs generic-only vs no signal."""
    data = d.get('ieir_breakdown', {})
    total = data.get('total', 0)
    explicit = data.get('campaign_specific', data.get('explicit', 0))
    implicit = data.get('generic_only', data.get('implicit_only', 0))
    none_sig = data.get('no_signal', 0)

    if total == 0:
        return "% No IEIR data available\n"

    explicit_pct = data.get('campaign_specific_pct', data.get('explicit_pct', 0))
    ieir_pct = data.get('ieir_pct', 0)
    none_pct = data.get('none_pct', 0)

    bar_h = 0.8  # cm
    scale = 0.08  # cm per percentage point

    lines = [
        "\\definecolor{acmBlue}{HTML}{1F77B4}",
        "\\definecolor{acmSand}{HTML}{D55E00}",
        "\\definecolor{acmGray}{HTML}{A0A0A0}",
        f"\\begin{{tikzpicture}}[y={bar_h}cm,x={scale}cm,font=\\footnotesize]",
        "  % Stacked bar",
    ]

    x = 0
    # Explicit platforms
    lines.append(f"  \\fill[acmBlue] ({x},0) rectangle ({x + explicit_pct},1);")
    if explicit_pct > 8:
        lines.append(
            f"  \\node[white,font=\\footnotesize] at ({x + explicit_pct / 2},0.5) "
            f"{{Explicit {fmt(explicit_pct)}\\%}};"
        )
    x += explicit_pct

    # Implicit only
    if ieir_pct > 0:
        lines.append(f"  \\fill[acmSand] ({x},0) rectangle ({x + ieir_pct},1);")
        if ieir_pct > 5:
            lines.append(
                f"  \\node[white] at ({x + ieir_pct / 2},0.5) "
                f"{{IEIR {fmt(ieir_pct)}\\%}};"
            )
        x += ieir_pct

    # No signal
    if none_pct > 0:
        lines.append(f"  \\fill[acmGray] ({x},0) rectangle ({x + none_pct},1);")
        x += none_pct

    # Border
    lines.append(f"  \\draw (0,0) rectangle (100,1);")

    # Legend
    lines.append(
        f"  \\node[anchor=west,font=\\scriptsize] at (0,-0.5) "
        f"{{$N={total}$ campaigns. "
        f"Explicit platform: {explicit} ({fmt(explicit_pct)}\\%), "
        f"IEIR (implicit-only): {implicit} ({fmt(ieir_pct)}\\%).}};"
    )

    # Confidence breakdown
    conf = data.get('confidence_breakdown', {})
    lines.append(
        f"  \\node[anchor=west,font=\\scriptsize,text=acmGray] at (0,-1.0) "
        f"{{Confidence: high={fmt(conf.get('high', 0))}\\%, "
        f"medium={fmt(conf.get('medium', 0))}\\%, "
        f"low={fmt(conf.get('low', 0))}\\%, "
        f"none={fmt(conf.get('none', 0))}\\%.}};"
    )

    lines.append("\\end{tikzpicture}")
    lines.append("")
    return "\n".join(lines)


def render_evidence_convergence(d):
    """Evidence convergence bar chart — convergent vs divergent."""
    data = d.get('evidence_convergence', {})
    total = data.get('total', 0)
    convergent = data.get('convergent', 0)
    divergent = data.get('divergent', 0)
    rate_pct = data.get('convergence_rate_pct', 0)

    if total == 0:
        return "% No convergence data available\n"

    bar_w = 2.0  # cm
    scale_y = 0.07  # cm per campaign

    lines = [
        "\\definecolor{acmBlue}{HTML}{1F77B4}",
        "\\definecolor{acmSand}{HTML}{D55E00}",
        "\\definecolor{acmGrid}{HTML}{D9DDE2}",
        f"\\begin{{tikzpicture}}[x={bar_w}cm,y={scale_y}cm,font=\\footnotesize]",
        f"  \\draw[->] (0,0) -- (0,{total + 5});",
    ]

    # Grid
    for y in range(0, total + 1, 10):
        lines.append(f"  \\draw[acmGrid] (-0.1,{y}) -- (2.5,{y});")
        lines.append(f"  \\node[left] at (-0.1,{y}) {{{y}}};")

    # Convergent bar
    lines.append(f"  \\fill[acmBlue] (0.2,0) rectangle (0.8,{convergent});")
    lines.append(f"  \\node[above] at (0.5,{convergent}) {{{convergent}}};")
    lines.append(f"  \\node[below] at (0.5,-2) {{Convergent}};")

    # Divergent bar
    lines.append(f"  \\fill[acmSand] (1.2,0) rectangle (1.8,{divergent});")
    lines.append(f"  \\node[above] at (1.5,{max(divergent, 1)}) {{{divergent}}};")
    lines.append(f"  \\node[below] at (1.5,-2) {{Divergent}};")

    # Annotation
    lines.append(
        f"  \\node[anchor=west,font=\\scriptsize] at (0,-6) "
        f"{{$N={total}$ campaigns. Convergence rate: {fmt(rate_pct)}\\%. "
        f"Mean signals/campaign: {fmt(data.get('mean_signal_count', 0))}.}};"
    )

    lines.append("\\end{tikzpicture}")
    lines.append("")
    return "\n".join(lines)


def main():
    d = json.loads((RESULTS / "figures_data.json").read_text(encoding="utf-8"))
    FIGS.mkdir(parents=True, exist_ok=True)

    # ── Original 8 figures ──
    (FIGS / "coverage_template.tex").write_text(render_coverage(d), encoding="utf-8")
    (FIGS / "tier_collapse_template.tex").write_text(render_tier_collapse(d), encoding="utf-8")
    (FIGS / "software_specificity_template.tex").write_text(render_software_specificity(d), encoding="utf-8")
    (FIGS / "cve_location_template.tex").write_text(render_cve_location(d), encoding="utf-8")
    (FIGS / "jaccard_cdf_template.tex").write_text(render_jaccard(d), encoding="utf-8")
    (FIGS / "ablation_template.tex").write_text(render_ablation(d), encoding="utf-8")
    (FIGS / "compatibility_distribution_template.tex").write_text(
        render_compatibility_distribution(d),
        encoding="utf-8",
    )
    (FIGS / "compatibility_by_tactic_template.tex").write_text(
        render_compatibility_by_tactic(d),
        encoding="utf-8",
    )

    # ── New figures: inNervoso consolidation ──
    n_new = 0
    if 'campaign_tactic_coverage' in d:
        (FIGS / "tactic_coverage_heatmap_template.tex").write_text(
            render_tactic_coverage_heatmap(d), encoding="utf-8"
        )
        n_new += 1

    if 'ieir_breakdown' in d:
        (FIGS / "ieir_breakdown_template.tex").write_text(
            render_ieir_breakdown(d), encoding="utf-8"
        )
        n_new += 1

    if 'evidence_convergence' in d:
        (FIGS / "evidence_convergence_template.tex").write_text(
            render_evidence_convergence(d), encoding="utf-8"
        )
        n_new += 1

    print(f"Rendered {8 + n_new} figure templates ({n_new} new) from measured JSON.")


if __name__ == "__main__":
    main()
