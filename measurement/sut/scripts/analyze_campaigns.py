#!/usr/bin/env python3
"""
analyze_campaigns.py  —  Paper 1 measurement pipeline
=====================================================
Generates ALL data missing from the Paper 1 figures that
sut_measurement_pipeline.py does NOT produce:

  1. Technique counts per tactic  →  chart.tex / chart_1.tex
  2. Campaign–technique binary matrix  →  clusters.tex (k-means k=7, n=51)
  3. Intrusion-set PCA scatter (real data)  →  nocluster.tex
  4. Silhouette score, LCS stats  →  values.tex macros
  5. Updated  results/values.tex  with all computed macros

Usage:
    python3 analyze_campaigns.py --bundle data/enterprise-attack.json
    python3 analyze_campaigns.py          # uses default path

Outputs (all in results/):
    paper1_tactic_counts.json
    paper1_pca_scatter.json
    paper1_clusters.json
    paper1_lcs.json
    figures/chart.tex          (overwrites with real data)
    figures/chart_1.tex        (same data, refined style)
    figures/nocluster.tex      (real PCA scatter)
    figures/clusters.tex       (real k-means clusters)
    ../../results/values.tex   (updated macros: silhouette, lcs*)

Authors: auto-generated fix for Paper 1 hardcoded figures
"""

import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import silhouette_score
from sklearn.preprocessing import StandardScaler

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).resolve().parent
DATA_DIR     = SCRIPT_DIR / "data"
RESULTS_DIR  = SCRIPT_DIR / "results"
WORKSPACE_ROOT = SCRIPT_DIR.parents[3]
FIGURES_DIR  = WORKSPACE_ROOT / "ACM CCS - Paper 1" / "figures"
VALUES_TEX   = WORKSPACE_ROOT / "ACM CCS - Paper 1" / "results" / "values.tex"

DEFAULT_BUNDLE = DATA_DIR / "enterprise-attack.json"

# k-means parameters (paper methodology)
KMEANS_K    = 7
KMEANS_SEED = 42
KMEANS_RUNS = 20   # n_init

# Tactic order for bar chart (descending count from the paper's chart)
TACTIC_DISPLAY_ORDER = [
    "defense-evasion",
    "persistence",
    "privilege-escalation",
    "credential-access",
    "execution",
    "command-and-control",
    "discovery",
    "resource-development",
    "reconnaissance",
    "collection",
    "impact",
    "lateral-movement",
    "initial-access",
    "exfiltration",
]

TACTIC_LABELS = {
    "defense-evasion":        "Defense Evasion",
    "persistence":            "Persistence",
    "privilege-escalation":   "Privilege Escalation",
    "credential-access":      "Credential Access",
    "execution":              "Execution",
    "command-and-control":    "Command And Control",
    "discovery":              "Discovery",
    "resource-development":   "Resource Development",
    "reconnaissance":         "Reconnaissance",
    "collection":             "Collection",
    "impact":                 "Impact",
    "lateral-movement":       "Lateral Movement",
    "initial-access":         "Initial Access",
    "exfiltration":           "Exfiltration",
}


# ── STIX helpers ───────────────────────────────────────────────────────────

def load_bundle(path: Path):
    with open(path, encoding="utf-8") as f:
        bundle = json.load(f)
    return bundle["objects"]


def active(obj):
    return not obj.get("x_mitre_deprecated") and not obj.get("revoked")


def index(objects):
    by_type = defaultdict(list)
    by_id   = {}
    for o in objects:
        if not active(o):
            continue
        by_type[o.get("type", "")].append(o)
        by_id[o["id"]] = o
    return by_type, by_id


def build_rel_index(relationships):
    fwd = defaultdict(list)   # source → [(rtype, target)]
    rev = defaultdict(list)   # target → [(rtype, source)]
    for r in relationships:
        s, t, rt = r.get("source_ref",""), r.get("target_ref",""), r.get("relationship_type","")
        fwd[s].append((rt, t))
        rev[t].append((rt, s))
    return fwd, rev


def external_id(obj):
    for ref in obj.get("external_references", []):
        if ref.get("source_name") == "mitre-attack":
            return ref.get("external_id", "")
    return ""


def technique_tactics(tech):
    return {
        ph["phase_name"]
        for ph in tech.get("kill_chain_phases", [])
        if ph.get("kill_chain_name") == "mitre-attack"
    }


# ── 1. Technique counts per tactic ─────────────────────────────────────────

def count_techniques_per_tactic(techniques):
    """Return dict tactic → count (sub-techniques counted individually)."""
    counter = Counter()
    for t in techniques:
        for tactic in technique_tactics(t):
            counter[tactic] += 1
    return counter


# ── 2. Campaign–technique binary matrix & k-means ──────────────────────────

def build_campaign_technique_matrix(campaigns, techniques, fwd, rev, excluded_ids):
    """
    Returns:
        matrix        : np.ndarray  shape (n_campaigns, n_techniques)
        campaign_names: list[str]
        tech_ids      : list[str]   STIX IDs
    """
    usable   = [c for c in campaigns if c["id"] not in excluded_ids]
    tech_ids = [t["id"] for t in techniques]
    tech_idx = {tid: i for i, tid in enumerate(tech_ids)}
    n_c, n_t = len(usable), len(tech_ids)

    matrix = np.zeros((n_c, n_t), dtype=np.float32)
    for i, camp in enumerate(usable):
        cid = camp["id"]
        linked = set()
        for rt, tgt in fwd.get(cid, []):
            if rt == "uses" and tgt in tech_idx:
                linked.add(tgt)
        for rt, src in rev.get(cid, []):
            if rt == "uses" and src in tech_idx:
                linked.add(src)
        for tid in linked:
            matrix[i, tech_idx[tid]] = 1.0

    names = [c.get("name", c["id"]) for c in usable]
    return matrix, names, tech_ids


def run_kmeans(matrix, k=KMEANS_K, seed=KMEANS_SEED):
    km = KMeans(n_clusters=k, n_init=KMEANS_RUNS, random_state=seed)
    labels = km.fit_predict(matrix)
    try:
        score = float(silhouette_score(matrix, labels))
    except Exception:
        score = float("nan")
    return labels, score


# ── 3. PCA scatter of intrusion-set technique vectors ──────────────────────

def build_is_technique_matrix(intrusion_sets, techniques, fwd, rev):
    """Binary IS × technique matrix for PCA."""
    tech_ids = [t["id"] for t in techniques]
    tech_idx = {tid: i for i, tid in enumerate(tech_ids)}
    n_is, n_t = len(intrusion_sets), len(tech_ids)

    matrix = np.zeros((n_is, n_t), dtype=np.float32)
    tech_counts = np.zeros(n_is, dtype=np.int32)

    for i, iset in enumerate(intrusion_sets):
        isid = iset["id"]
        linked = set()
        for rt, tgt in fwd.get(isid, []):
            if rt == "uses" and tgt in tech_idx:
                linked.add(tgt)
        for rt, src in rev.get(isid, []):
            if rt == "uses" and src in tech_idx:
                linked.add(src)
        for tid in linked:
            matrix[i, tech_idx[tid]] = 1.0
        tech_counts[i] = len(linked)

    names = [iset.get("name", iset["id"]) for iset in intrusion_sets]
    return matrix, tech_counts, names


def run_pca_scatter(matrix, tech_counts):
    """Returns (pc1, pc2) coordinates and colour values (tech count)."""
    pca = PCA(n_components=2, random_state=KMEANS_SEED)
    coords = pca.fit_transform(matrix)
    return coords[:, 0].tolist(), coords[:, 1].tolist(), tech_counts.tolist()


# ── 4. LCS (Longest Common Subsequence) between campaign technique sequences─

def lcs_length(a, b):
    """Standard DP LCS length."""
    m, n = len(a), len(b)
    if m == 0 or n == 0:
        return 0
    # Space-optimised O(min(m,n)) rows
    if m < n:
        a, b = b, a
        m, n = n, m
    prev = [0] * (n + 1)
    for i in range(1, m + 1):
        curr = [0] * (n + 1)
        for j in range(1, n + 1):
            if a[i-1] == b[j-1]:
                curr[j] = prev[j-1] + 1
            else:
                curr[j] = max(prev[j], curr[j-1])
        prev = curr
    return prev[n]


def campaign_technique_sequences(campaigns, techniques, fwd, rev, excluded_ids, by_id):
    """
    For each campaign return the ordered sequence of technique external IDs
    sorted by tactic kill-chain order.
    """
    TACTIC_ORDER_LIST = [
        "reconnaissance", "resource-development", "initial-access", "execution",
        "persistence", "privilege-escalation", "defense-evasion", "credential-access",
        "discovery", "lateral-movement", "collection", "command-and-control",
        "exfiltration", "impact",
    ]
    tactic_rank = {t: i for i, t in enumerate(TACTIC_ORDER_LIST)}
    tech_set = {t["id"] for t in techniques}

    seqs = []
    usable = [c for c in campaigns if c["id"] not in excluded_ids]
    for camp in usable:
        cid = camp["id"]
        linked = set()
        for rt, tgt in fwd.get(cid, []):
            if rt == "uses" and tgt in tech_set:
                linked.add(tgt)
        for rt, src in rev.get(cid, []):
            if rt == "uses" and src in tech_set:
                linked.add(src)

        def sort_key(tid):
            tech = by_id.get(tid)
            if not tech:
                return 99
            tactics = technique_tactics(tech)
            return min((tactic_rank.get(t, 99) for t in tactics), default=99)

        seq = sorted(linked, key=sort_key)
        seqs.append([external_id(by_id[tid]) for tid in seq if by_id.get(tid)])

    return seqs


def compute_lcs_stats(seqs):
    """Compute mean/median/max pairwise LCS length across all campaign pairs."""
    lengths = []
    n = len(seqs)
    for i in range(n):
        for j in range(i + 1, n):
            lengths.append(lcs_length(seqs[i], seqs[j]))
    if not lengths:
        return 0.0, 0.0, 0
    mean_v   = round(sum(lengths) / len(lengths), 1)
    sorted_l = sorted(lengths)
    mid      = len(sorted_l) // 2
    median_v = float(sorted_l[mid]) if len(sorted_l) % 2 == 1 \
               else round((sorted_l[mid-1] + sorted_l[mid]) / 2, 1)
    max_v    = max(lengths)
    return mean_v, median_v, max_v


# ── TikZ renderers ─────────────────────────────────────────────────────────

def render_chart_tex(tactic_counts: dict, style: str = "original") -> str:
    """
    Render chart.tex (technique count by tactic, horizontal bar chart).
    style = "original" | "refined"
    """
    counts_ordered = []
    for tactic in TACTIC_DISPLAY_ORDER:
        counts_ordered.append(tactic_counts.get(tactic, 0))

    total = sum(tactic_counts.values())
    max_count = max(counts_ordered) if counts_ordered else 300
    ymax = math.ceil(max_count / 50) * 50 + 50

    labels_tex = ",\n    ".join(
        "{" + TACTIC_LABELS.get(t, t) + "}" for t in TACTIC_DISPLAY_ORDER
    )
    yticks = ",".join(str(v) for v in range(0, ymax + 1, 50))

    if style == "original":
        color_def = r"""
\providecolor{execblue}{HTML}{1F618D}
\providecolor{midgray} {HTML}{7F8C8D}
\providecolor{dashgray}{HTML}{95A5A6}
\colorlet{bc1} {execblue!12}
\colorlet{bc2} {execblue!20}
\colorlet{bc3} {execblue!30}
\colorlet{bc4} {execblue!42}
\colorlet{bc5} {execblue!54}
\colorlet{bc6} {execblue!66}
\colorlet{bc7} {execblue!78}
\colorlet{bc8} {execblue!90}
\colorlet{bc9} {execblue!85!black}
\colorlet{bc10}{execblue!73!black}
\colorlet{bc11}{execblue!61!black}
\colorlet{bc12}{execblue!50!black}
\colorlet{bc13}{execblue!40!black}
\colorlet{bc14}{execblue!31!black}"""
        bar_cmd = r"""\newcommand{\mybar}[4]{%
  \fill[#3] (axis cs:{#1-0.38},0) rectangle (axis cs:{#1+0.38},{#2});
  \node[font=\normalsize\bfseries,
        fill=white, draw=black!65, rounded corners=2.5pt, inner sep=2.5pt]
    at (axis cs:{#1},{#2+9}) {#4};
}"""
        axis_opts = rf"""  name         = myax,
  width        = 18cm,
  height       = 10.7cm,
  xmin=0.5, xmax=14.5,
  xtick        = {{1,2,3,4,5,6,7,8,9,10,11,12,13,14}},
  xticklabels  = {{
    {labels_tex}}},
  xticklabel style = {{rotate=45, anchor=east, font=\normalsize}},
  ymin=0, ymax={ymax},
  ytick        = {{{yticks}}},
  yticklabel style = {{font=\normalsize}},
  ymajorgrids  = true,
  grid style   = {{dashgray!45, thin, dashed}},
  extra y ticks       = {{0}},
  extra y tick labels = {{}},
  extra y tick style  = {{grid=major, grid style={{black!55, thin, solid}}}},
  axis line style = {{draw=none}},
  tick style   = {{draw=none}},
  clip         = false"""
        bars = "\n".join(
            rf"\mybar{{{i+1}}}{{{counts_ordered[i]}}}{{bc{i+1}}}{{{counts_ordered[i]}}}"
            for i in range(len(counts_ordered))
        )
        footer_label = rf"""\node[font=\normalsize\itshape, text=midgray, anchor=north west]
  at ($(current bounding box.south west)+(0.1,0.12)$)
  {{\textit{{Total Techniques: {total}}}}}"""
        return rf"""% chart.tex — Technique count by tactic (AUTO-GENERATED from real data)
% Generated by analyze_campaigns.py — DO NOT EDIT BY HAND
{color_def}
{bar_cmd}
\begin{{tikzpicture}}
\begin{{axis}}[
{axis_opts},
  clip=false
]
{bars}
\end{{axis}}
{footer_label};
\end{{tikzpicture}}
"""
    else:  # refined
        color_def = r"""
\providecolor{execblue}{HTML}{1F618D}
\providecolor{midgray}{HTML}{4D4D4D}
\providecolor{dashgray}{HTML}{BDBDBD}
\providecolor{facegray}{HTML}{F2F2F2}
\providecolor{edgegray}{HTML}{4A4A4A}
\providecolor{boxedge}{HTML}{8E8E8E}
\colorlet{bc1} {execblue!12!white}
\colorlet{bc2} {execblue!20!white}
\colorlet{bc3} {execblue!29!white}
\colorlet{bc4} {execblue!39!white}
\colorlet{bc5} {execblue!49!white}
\colorlet{bc6} {execblue!58!white}
\colorlet{bc7} {execblue!66!white}
\colorlet{bc8} {execblue!74!white}
\colorlet{bc9} {execblue!82!black}
\colorlet{bc10}{execblue!72!black}
\colorlet{bc11}{execblue!63!black}
\colorlet{bc12}{execblue!54!black}
\colorlet{bc13}{execblue!46!black}
\colorlet{bc14}{execblue!39!black}"""
        bar_cmd = r"""\newcommand{\barbox}[4]{%
  \path[draw=edgegray, line width=0.45pt, fill=#3]
    (axis cs:{#1-0.40},0) rectangle (axis cs:{#1+0.40},{#2});
  \node[
    font=\bfseries\fontsize{13}{13}\selectfont,
    fill=white,
    draw=boxedge,
    line width=0.45pt,
    rounded corners=2.5pt,
    inner xsep=3.2pt,
    inner ysep=1.8pt,
    text=black
  ] at (axis cs:#1,{#2+7}) {#4};
}"""
        axis_opts = rf"""  width=18.7cm,
  height=11.15cm,
  xmin=0.45, xmax=14.55,
  ymin=0, ymax={ymax},
  axis background/.style={{fill=facegray}},
  axis line style={{draw=edgegray, line width=0.45pt}},
  ymajorgrids=true,
  xmajorgrids=false,
  grid style={{draw=dashgray, dash pattern=on 3pt off 2pt, line width=0.35pt}},
  tick align=outside,
  tick style={{draw=edgegray, line width=0.4pt}},
  xtick={{1,2,3,4,5,6,7,8,9,10,11,12,13,14}},
  xticklabels={{
    {labels_tex}}},
  xticklabel style={{rotate=45, anchor=east, font=\bfseries\fontsize{{11}}{{12}}\selectfont, text=black}},
  ytick={{{yticks}}},
  yticklabel style={{font=\fontsize{{11}}{{12}}\selectfont, text=black}},
  clip=false"""
        bars = "\n".join(
            rf"\barbox{{{i+1}}}{{{counts_ordered[i]}}}{{bc{i+1}}}{{{counts_ordered[i]}}}"
            for i in range(len(counts_ordered))
        )
        return rf"""% chart_1.tex — Technique count by tactic, refined style (AUTO-GENERATED)
% Generated by analyze_campaigns.py — DO NOT EDIT BY HAND
{color_def}
{bar_cmd}
\begin{{tikzpicture}}
\begin{{axis}}[
{axis_opts}
]
{bars}
\end{{axis}}
\node[
  font=\itshape\fontsize{{13}}{{13}}\selectfont,
  text=midgray,
  anchor=north west
] at ($(current bounding box.south west)+(0.03,-0.58)$)
  {{Total Techniques: {total}}};
\end{{tikzpicture}}
"""


def render_nocluster_tex(pc1, pc2, tech_counts) -> str:
    """Real PCA scatter plot (replaces synthetic approximation)."""
    coords_str = "\n".join(
        f"({x:.2f},{y:.2f})[{c}]"
        for x, y, c in zip(pc1, pc2, tech_counts)
    )
    x_min = math.floor(min(pc1)) - 1
    x_max = math.ceil(max(pc1)) + 2
    y_min = math.floor(min(pc2)) - 2
    y_max = math.ceil(max(pc2)) + 3
    c_max = max(tech_counts)
    c_max_tick = math.ceil(c_max / 20) * 20

    return rf"""% nocluster.tex — PCA scatter of {len(pc1)} intrusion-set technique vectors
% AUTO-GENERATED by analyze_campaigns.py — DO NOT EDIT BY HAND
% Points are REAL data from ATT&CK Enterprise v18.1, NOT synthetic.
\pgfplotsset{{
  colormap={{viridis}}{{
    rgb255=(68,  1, 84)
    rgb255=(72, 35,116)
    rgb255=(64, 67,135)
    rgb255=(52, 94,141)
    rgb255=(41,120,142)
    rgb255=(32,144,141)
    rgb255=(34,167,133)
    rgb255=(68,190,112)
    rgb255=(121,209, 81)
    rgb255=(189,222, 38)
    rgb255=(253,231, 37)
  }}
}}
\begin{{tikzpicture}}
\begin{{axis}}[
  scale only axis,
  width  = 8.5cm,
  height = 8.5cm,
  xlabel = {{Principal Component 1}},
  ylabel = {{Principal Component 2}},
  xlabel style = {{font=\small}},
  ylabel style = {{font=\small}},
  xmin={x_min}, xmax={x_max},
  ymin={y_min},  ymax={y_max},
  tick label style = {{font=\small}},
  axis lines     = box,
  axis line style = {{black, thin}},
  tick style     = {{black, thin}},
  grid       = both,
  grid style = {{gray!22, thin}},
  minor tick num = 0,
  colormap name = viridis,
  colorbar,
  colorbar style = {{
    width            = 0.3cm,
    ylabel           = {{Number of Techniques}},
    ylabel style     = {{font=\small, yshift=3pt}},
    yticklabel style = {{font=\small}},
    ytick            = {{0,{c_max_tick // 4},{c_max_tick // 2},{3 * c_max_tick // 4},{c_max_tick}}},
  }},
  point meta min = 0,
  point meta max = {c_max},
  scatter,
  scatter src  = explicit,
  only marks,
  mark         = *,
  mark size    = 3.8pt,
  mark options = {{draw opacity=0.85, fill opacity=0.85, line width=0.3pt}},
]
\addplot[scatter, only marks, scatter src=explicit] coordinates {{
{coords_str}
}};
\end{{axis}}
\end{{tikzpicture}}
"""


def render_clusters_tex(campaign_names, labels, matrix, n_clusters=KMEANS_K) -> str:
    """
    Bubble diagram for k-means clusters (replicates clusters.tex style).
    Bubble radius ∝ sqrt(cluster_size); positions laid out in a circle.
    """
    cluster_sizes = Counter(labels.tolist())

    # Compute cluster centroids and intra-cluster shared techniques
    n_techniques = matrix.shape[1]
    shared_techs_per_cluster = {}
    for k in range(n_clusters):
        members = matrix[labels == k]
        if len(members) > 1:
            # "Shared" = technique present in ALL members of cluster
            shared = int((members.sum(axis=0) == len(members)).sum())
        else:
            shared = int(members.sum()) if len(members) == 1 else 0
        shared_techs_per_cluster[k] = shared

    # Sort clusters by size descending (largest first = Cluster 1)
    sorted_clusters = sorted(range(n_clusters), key=lambda k: -cluster_sizes[k])

    # matplotlib tab10 palette (exact RGB)
    TAB10 = [
        (31, 119, 180),   # blue
        (255, 127,  14),  # orange
        (214,  39,  40),  # red
        (140,  86,  75),  # brown
        (227, 119, 194),  # pink
        (188, 189,  34),  # olive
        ( 23, 190, 207),  # cyan
    ]

    # Layout: circular arrangement
    center_x, center_y = 2.5, 3.5
    layout_radius = 3.8
    positions = []
    for i in range(n_clusters):
        angle = 2 * math.pi * i / n_clusters - math.pi / 2
        x = center_x + layout_radius * math.cos(angle)
        y = center_y + layout_radius * math.sin(angle)
        positions.append((x, y))

    color_defs = ""
    fills      = ""
    labels_tex = ""

    for idx, k in enumerate(sorted_clusters):
        cluster_num = idx + 1
        size = cluster_sizes[k]
        shared = shared_techs_per_cluster[k]
        r_g_b = TAB10[idx % len(TAB10)]
        x, y = positions[idx]
        radius = 0.9 + 0.45 * math.sqrt(size)

        color_defs += (
            f"\\definecolor{{cl{cluster_num}}}{{RGB}}{{{r_g_b[0]},{r_g_b[1]},{r_g_b[2]}}}"
            f"  % Cluster {cluster_num} ({size} campaigns)\n"
        )
        fills += (
            f"  \\fill[cl{cluster_num}, fill opacity=0.55] "
            f"({x:.1f}, {y:.1f})  circle ({radius:.2f}cm);\n"
        )
        labels_tex += (
            f"\\node[lbox] at ({x:.1f}, {y:.1f}) "
            f"{{Cluster {cluster_num}\\\\Campaigns: {size}\\\\Shared Tech: {shared}}};\n"
        )

    return rf"""% clusters.tex — Campaign clusters (k={n_clusters}, n={sum(cluster_sizes.values())}) bubble diagram
% AUTO-GENERATED by analyze_campaigns.py — DO NOT EDIT BY HAND
{color_defs.rstrip()}
\begin{{tikzpicture}}[font=\footnotesize]
\begin{{scope}}[blend group=multiply]
{fills.rstrip()}
\end{{scope}}
\tikzset{{lbox/.style={{
  draw=black!80, fill=white, rounded corners=4pt,
  inner sep=5pt, align=center, font=\footnotesize\bfseries, line width=0.6pt
}}}}
{labels_tex.rstrip()}
\end{{tikzpicture}}
"""


# ── values.tex updater ─────────────────────────────────────────────────────

def update_values_tex(values_tex_path: Path, updates: dict):
    """
    Update (or append) \\newcommand entries in values.tex.
    updates = {latex_key: value}
    """
    if not values_tex_path.exists():
        print(f"[WARN] values.tex not found at {values_tex_path}; skipping update.")
        return

    text = values_tex_path.read_text(encoding="utf-8")
    for key, val in updates.items():
        pattern = rf"(\\newcommand\{{\\{re.escape(key)}\}})\{{[^}}]*\}}"
        replacement = rf"\1{{{val}}}"
        new_text = re.sub(pattern, replacement, text)
        if new_text == text:
            # Not found — append
            text = new_text + f"\\newcommand{{\\{key}}}{{{val}}}\n"
        else:
            text = new_text

    values_tex_path.write_text(text, encoding="utf-8")
    print(f"  ✓ Updated {values_tex_path}")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        default=str(DEFAULT_BUNDLE),
        help="Path to enterprise-attack.json STIX bundle",
    )
    parser.add_argument(
        "--no-write-figures",
        action="store_true",
        help="Compute data but do not overwrite .tex figure files",
    )
    args = parser.parse_args()

    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        sys.exit(f"[ERROR] Bundle not found: {bundle_path}")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Paper 1 — analyze_campaigns.py")
    print(f"Bundle : {bundle_path}")
    print("=" * 70)

    # ── Load bundle ──────────────────────────────────────────────
    print("\n[1/5] Loading STIX bundle...")
    all_objects      = load_bundle(bundle_path)
    by_type, by_id   = index(all_objects)
    relationships    = by_type.get("relationship", [])
    fwd, rev         = build_rel_index(relationships)

    techniques       = by_type.get("attack-pattern", [])
    campaigns        = by_type.get("campaign", [])
    intrusion_sets   = by_type.get("intrusion-set", [])

    print(f"  Techniques     : {len(techniques)}")
    print(f"  Campaigns      : {len(campaigns)}")
    print(f"  Intrusion Sets : {len(intrusion_sets)}")

    # Identify excluded campaigns (no 'uses' rels)
    excluded_ids = set()
    for c in campaigns:
        if not any(rt == "uses" for rt, _ in fwd.get(c["id"], [])):
            excluded_ids.add(c["id"])
    print(f"  Excluded campaigns (no rels): {len(excluded_ids)}")

    # ── 1. Tactic counts ─────────────────────────────────────────
    print("\n[2/5] Counting techniques per tactic...")
    tactic_counts = count_techniques_per_tactic(techniques)
    total_tactic_refs = sum(tactic_counts.values())
    print(f"  Total tactic-technique refs: {total_tactic_refs}")
    for t in TACTIC_DISPLAY_ORDER:
        print(f"  {TACTIC_LABELS[t]:<30}: {tactic_counts.get(t, 0)}")

    (RESULTS_DIR / "paper1_tactic_counts.json").write_text(
        json.dumps({"tactic_counts": dict(tactic_counts), "total": total_tactic_refs}, indent=2),
        encoding="utf-8",
    )

    # ── 2. Campaign k-means clustering ───────────────────────────
    print(f"\n[3/5] Building campaign–technique matrix and running k-means (k={KMEANS_K})...")
    camp_matrix, camp_names, tech_ids = build_campaign_technique_matrix(
        campaigns, techniques, fwd, rev, excluded_ids
    )
    n_campaigns = camp_matrix.shape[0]
    print(f"  Matrix shape: {camp_matrix.shape}  (campaigns × techniques)")

    cluster_labels, silhouette = run_kmeans(camp_matrix)
    print(f"  Silhouette score (k={KMEANS_K}): {silhouette:.4f}")

    cluster_sizes = Counter(cluster_labels.tolist())
    print(f"  Cluster sizes: {dict(sorted(cluster_sizes.items()))}")

    cluster_data = {
        "n_campaigns": n_campaigns,
        "k": KMEANS_K,
        "silhouette_score": round(silhouette, 4),
        "cluster_sizes": dict(cluster_sizes),
        "campaign_clusters": [
            {"campaign": camp_names[i], "cluster": int(cluster_labels[i])}
            for i in range(n_campaigns)
        ],
    }
    (RESULTS_DIR / "paper1_clusters.json").write_text(
        json.dumps(cluster_data, indent=2), encoding="utf-8"
    )

    # Baseline silhouette (random permutation, 100 iterations)
    rng = np.random.default_rng(KMEANS_SEED)
    baseline_scores = []
    for _ in range(100):
        shuffled = rng.permutation(cluster_labels)
        try:
            s = float(silhouette_score(camp_matrix, shuffled))
        except Exception:
            s = 0.0
        baseline_scores.append(s)
    sil_baseline_mean = round(float(np.mean(baseline_scores)), 4)
    sil_baseline_std  = round(float(np.std(baseline_scores)), 4)
    print(f"  Silhouette baseline (random): mean={sil_baseline_mean}, std={sil_baseline_std}")

    # ── 3. Intrusion-set PCA scatter ─────────────────────────────
    print(f"\n[4/5] Running PCA on {len(intrusion_sets)} intrusion-set technique vectors...")
    is_matrix, is_tech_counts, is_names = build_is_technique_matrix(
        intrusion_sets, techniques, fwd, rev
    )
    pc1, pc2, counts_list = run_pca_scatter(is_matrix, is_tech_counts)
    print(f"  PCA complete. PC1 range: [{min(pc1):.1f}, {max(pc1):.1f}]")
    print(f"  Tech count range: [{min(counts_list)}, {max(counts_list)}]")

    pca_data = {
        "n_intrusion_sets": len(intrusion_sets),
        "pc1": [round(v, 4) for v in pc1],
        "pc2": [round(v, 4) for v in pc2],
        "tech_counts": counts_list,
        "names": is_names,
    }
    (RESULTS_DIR / "paper1_pca_scatter.json").write_text(
        json.dumps(pca_data, indent=2), encoding="utf-8"
    )

    # ── 4. LCS stats ─────────────────────────────────────────────
    print("\n[5/5] Computing LCS stats (pairwise campaign technique sequences)...")
    seqs = campaign_technique_sequences(campaigns, techniques, fwd, rev, excluded_ids, by_id)
    print(f"  Computing pairwise LCS for {len(seqs)} campaigns...")
    lcs_mean, lcs_median, lcs_max = compute_lcs_stats(seqs)
    print(f"  LCS mean={lcs_mean}, median={lcs_median}, max={lcs_max}")

    lcs_data = {
        "n_campaigns": len(seqs),
        "mean": lcs_mean,
        "median": lcs_median,
        "max": lcs_max,
    }
    (RESULTS_DIR / "paper1_lcs.json").write_text(
        json.dumps(lcs_data, indent=2), encoding="utf-8"
    )

    # ── Write figure files ────────────────────────────────────────
    if not args.no_write_figures:
        print("\n[Figures] Writing TikZ figure files...")

        chart_tex = render_chart_tex(tactic_counts, style="original")
        (FIGURES_DIR / "chart.tex").write_text(chart_tex, encoding="utf-8")
        print(f"  ✓ chart.tex  ({FIGURES_DIR / 'chart.tex'})")

        chart1_tex = render_chart_tex(tactic_counts, style="refined")
        (FIGURES_DIR / "chart_1.tex").write_text(chart1_tex, encoding="utf-8")
        print(f"  ✓ chart_1.tex")

        nocluster_tex = render_nocluster_tex(pc1, pc2, counts_list)
        (FIGURES_DIR / "nocluster.tex").write_text(nocluster_tex, encoding="utf-8")
        print(f"  ✓ nocluster.tex  (REAL PCA data, not synthetic)")

        clusters_tex = render_clusters_tex(camp_names, cluster_labels, camp_matrix, KMEANS_K)
        (FIGURES_DIR / "clusters.tex").write_text(clusters_tex, encoding="utf-8")
        print(f"  ✓ clusters.tex")
    else:
        print("\n[Figures] Skipped (--no-write-figures).")

    # ── Update values.tex ─────────────────────────────────────────
    print("\n[values.tex] Updating Paper 1 macros...")
    updates = {
        "silhouetteScore":       f"{silhouette:.2f}",
        "silhouetteBaselineMean": f"{sil_baseline_mean:.2f}",
        "silhouetteBaselineStd":  f"{sil_baseline_std:.2f}",
        "lcsLengthMean":          f"{lcs_mean}",
        "lcsLengthMedian":        f"{lcs_median}",
        "lcsLengthMax":           f"{lcs_max}",
    }
    update_values_tex(VALUES_TEX, updates)

    # ── Summary ───────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Techniques (total tactic refs) : {total_tactic_refs}")
    print(f"  Campaigns clustered            : {n_campaigns}  (k={KMEANS_K})")
    print(f"  Silhouette score               : {silhouette:.4f}")
    print(f"  Silhouette baseline            : {sil_baseline_mean:.4f} ± {sil_baseline_std:.4f}")
    print(f"  Intrusion sets in PCA          : {len(intrusion_sets)}")
    print(f"  LCS mean / median / max        : {lcs_mean} / {lcs_median} / {lcs_max}")
    print()
    print("Output files:")
    print(f"  {RESULTS_DIR / 'paper1_tactic_counts.json'}")
    print(f"  {RESULTS_DIR / 'paper1_clusters.json'}")
    print(f"  {RESULTS_DIR / 'paper1_pca_scatter.json'}")
    print(f"  {RESULTS_DIR / 'paper1_lcs.json'}")
    if not args.no_write_figures:
        print(f"  {FIGURES_DIR / 'chart.tex'}  (REAL DATA)")
        print(f"  {FIGURES_DIR / 'chart_1.tex'}  (REAL DATA)")
        print(f"  {FIGURES_DIR / 'nocluster.tex'}  (REAL PCA)")
        print(f"  {FIGURES_DIR / 'clusters.tex'}  (REAL CLUSTERS)")
    print(f"  {VALUES_TEX}  (updated macros)")


if __name__ == "__main__":
    main()
