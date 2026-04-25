"""Quick vault topology visualizer."""
import os
import re
import yaml
import networkx as nx
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

VAULT = "~/loci/vault"

TYPE_COLORS = {
    "project":      "#4e79a7",
    "task":         "#f28e2b",
    "document":     "#59a14f",
    "entity":       "#e15759",
    "conversation": "#76b7b2",
    "article":      "#edc948",
    "bookmark":     "#b07aa1",
    "procedure":    "#ff9da7",
    "topic":        "#9c755f",
}
DEFAULT_COLOR = "#bab0ac"

def parse_frontmatter(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return None
    try:
        return yaml.safe_load(m.group(1))
    except yaml.YAMLError as e:
        print(f"skipping {path}: {e}")
        return None

def load_nodes():
    nodes = {}
    for fname in os.listdir(VAULT):
        if not fname.endswith(".md"):
            continue
        fm = parse_frontmatter(os.path.join(VAULT, fname))
        if not fm or "uid" not in fm:
            continue
        nodes[fm["uid"]] = {
            "title": fm.get("title", fname),
            "type":  fm.get("type", "unknown"),
            "relations": fm.get("relations") or [],
        }
    return nodes

def build_graph(nodes):
    G = nx.DiGraph()
    for uid, data in nodes.items():
        G.add_node(uid, **data)
    for uid, data in nodes.items():
        for rel in data["relations"]:
            target = rel.get("uid")
            rtype  = rel.get("type", "relates-to")
            if target and target in nodes:
                G.add_edge(uid, target, relation=rtype)
    return G

def draw(G, nodes):
    fig, ax = plt.subplots(figsize=(20, 14))
    fig.patch.set_facecolor("#1e1e2e")
    ax.set_facecolor("#1e1e2e")

    pos = nx.spring_layout(G, k=2.5, iterations=80, seed=42)

    node_colors = [TYPE_COLORS.get(nodes[n]["type"], DEFAULT_COLOR) for n in G.nodes()]
    labels = {n: nodes[n]["title"][:24] for n in G.nodes()}

    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=600,
                           alpha=0.9, ax=ax)
    nx.draw_networkx_labels(G, pos, labels, font_size=6,
                            font_color="white", ax=ax)
    nx.draw_networkx_edges(G, pos, edge_color="#888888", arrows=True,
                           arrowsize=10, width=0.7, alpha=0.6,
                           connectionstyle="arc3,rad=0.05", ax=ax)

    legend = [mpatches.Patch(color=c, label=t)
              for t, c in TYPE_COLORS.items()]
    ax.legend(handles=legend, loc="upper left", fontsize=8,
              facecolor="#2a2a3e", edgecolor="none", labelcolor="white")

    ax.set_title("Loci vault topology", color="white", fontsize=14, pad=10)
    ax.axis("off")
    plt.tight_layout()
    out = "/tmp/loci_topology.png"
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
    print(f"Saved → {out}")
    # plt.show()  # not available headless

if __name__ == "__main__":
    nodes = load_nodes()
    G = build_graph(nodes)
    print(f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges")
    # quick stats
    isolated = [n for n in G.nodes() if G.degree(n) == 0]
    print(f"Isolated (no links): {len(isolated)}")
    draw(G, nodes)
