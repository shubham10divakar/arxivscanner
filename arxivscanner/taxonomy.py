"""Built-in map of arXiv domains (archives) and subdomains (categories), plus a terminal picker."""
from __future__ import annotations

import re
import shlex
from typing import Dict, List, Optional, Tuple

# domain code -> (domain name, {subdomain code: subdomain name})
# Domains with no subdomains (quant-ph, hep-th, ...) are categories in their own right.
DOMAINS: Dict[str, Tuple[str, Dict[str, str]]] = {
    "cs": ("Computer Science", {
        "cs.AI": "Artificial Intelligence",
        "cs.AR": "Hardware Architecture",
        "cs.CC": "Computational Complexity",
        "cs.CE": "Computational Engineering, Finance, and Science",
        "cs.CG": "Computational Geometry",
        "cs.CL": "Computation and Language",
        "cs.CR": "Cryptography and Security",
        "cs.CV": "Computer Vision and Pattern Recognition",
        "cs.CY": "Computers and Society",
        "cs.DB": "Databases",
        "cs.DC": "Distributed, Parallel, and Cluster Computing",
        "cs.DL": "Digital Libraries",
        "cs.DM": "Discrete Mathematics",
        "cs.DS": "Data Structures and Algorithms",
        "cs.ET": "Emerging Technologies",
        "cs.FL": "Formal Languages and Automata Theory",
        "cs.GL": "General Literature",
        "cs.GR": "Graphics",
        "cs.GT": "Computer Science and Game Theory",
        "cs.HC": "Human-Computer Interaction",
        "cs.IR": "Information Retrieval",
        "cs.IT": "Information Theory",
        "cs.LG": "Machine Learning",
        "cs.LO": "Logic in Computer Science",
        "cs.MA": "Multiagent Systems",
        "cs.MM": "Multimedia",
        "cs.MS": "Mathematical Software",
        "cs.NA": "Numerical Analysis",
        "cs.NE": "Neural and Evolutionary Computing",
        "cs.NI": "Networking and Internet Architecture",
        "cs.OH": "Other Computer Science",
        "cs.OS": "Operating Systems",
        "cs.PF": "Performance",
        "cs.PL": "Programming Languages",
        "cs.RO": "Robotics",
        "cs.SC": "Symbolic Computation",
        "cs.SD": "Sound",
        "cs.SE": "Software Engineering",
        "cs.SI": "Social and Information Networks",
        "cs.SY": "Systems and Control",
    }),
    "eess": ("Electrical Engineering and Systems Science", {
        "eess.AS": "Audio and Speech Processing",
        "eess.IV": "Image and Video Processing",
        "eess.SP": "Signal Processing",
        "eess.SY": "Systems and Control",
    }),
    "stat": ("Statistics", {
        "stat.AP": "Applications",
        "stat.CO": "Computation",
        "stat.ME": "Methodology",
        "stat.ML": "Machine Learning",
        "stat.OT": "Other Statistics",
        "stat.TH": "Statistics Theory",
    }),
    "math": ("Mathematics", {
        "math.AC": "Commutative Algebra",
        "math.AG": "Algebraic Geometry",
        "math.AP": "Analysis of PDEs",
        "math.AT": "Algebraic Topology",
        "math.CA": "Classical Analysis and ODEs",
        "math.CO": "Combinatorics",
        "math.CT": "Category Theory",
        "math.CV": "Complex Variables",
        "math.DG": "Differential Geometry",
        "math.DS": "Dynamical Systems",
        "math.FA": "Functional Analysis",
        "math.GM": "General Mathematics",
        "math.GN": "General Topology",
        "math.GR": "Group Theory",
        "math.GT": "Geometric Topology",
        "math.HO": "History and Overview",
        "math.IT": "Information Theory",
        "math.KT": "K-Theory and Homology",
        "math.LO": "Logic",
        "math.MG": "Metric Geometry",
        "math.MP": "Mathematical Physics",
        "math.NA": "Numerical Analysis",
        "math.NT": "Number Theory",
        "math.OA": "Operator Algebras",
        "math.OC": "Optimization and Control",
        "math.PR": "Probability",
        "math.QA": "Quantum Algebra",
        "math.RA": "Rings and Algebras",
        "math.RT": "Representation Theory",
        "math.SG": "Symplectic Geometry",
        "math.SP": "Spectral Theory",
        "math.ST": "Statistics Theory",
    }),
    "q-bio": ("Quantitative Biology", {
        "q-bio.BM": "Biomolecules",
        "q-bio.CB": "Cell Behavior",
        "q-bio.GN": "Genomics",
        "q-bio.MN": "Molecular Networks",
        "q-bio.NC": "Neurons and Cognition",
        "q-bio.OT": "Other Quantitative Biology",
        "q-bio.PE": "Populations and Evolution",
        "q-bio.QM": "Quantitative Methods",
        "q-bio.SC": "Subcellular Processes",
        "q-bio.TO": "Tissues and Organs",
    }),
    "q-fin": ("Quantitative Finance", {
        "q-fin.CP": "Computational Finance",
        "q-fin.EC": "Economics",
        "q-fin.GN": "General Finance",
        "q-fin.MF": "Mathematical Finance",
        "q-fin.PM": "Portfolio Management",
        "q-fin.PR": "Pricing of Securities",
        "q-fin.RM": "Risk Management",
        "q-fin.ST": "Statistical Finance",
        "q-fin.TR": "Trading and Market Microstructure",
    }),
    "econ": ("Economics", {
        "econ.EM": "Econometrics",
        "econ.GN": "General Economics",
        "econ.TH": "Theoretical Economics",
    }),
    "astro-ph": ("Astrophysics", {
        "astro-ph.CO": "Cosmology and Nongalactic Astrophysics",
        "astro-ph.EP": "Earth and Planetary Astrophysics",
        "astro-ph.GA": "Astrophysics of Galaxies",
        "astro-ph.HE": "High Energy Astrophysical Phenomena",
        "astro-ph.IM": "Instrumentation and Methods for Astrophysics",
        "astro-ph.SR": "Solar and Stellar Astrophysics",
    }),
    "cond-mat": ("Condensed Matter", {
        "cond-mat.dis-nn": "Disordered Systems and Neural Networks",
        "cond-mat.mes-hall": "Mesoscale and Nanoscale Physics",
        "cond-mat.mtrl-sci": "Materials Science",
        "cond-mat.other": "Other Condensed Matter",
        "cond-mat.quant-gas": "Quantum Gases",
        "cond-mat.soft": "Soft Condensed Matter",
        "cond-mat.stat-mech": "Statistical Mechanics",
        "cond-mat.str-el": "Strongly Correlated Electrons",
        "cond-mat.supr-con": "Superconductivity",
    }),
    "physics": ("Physics", {
        "physics.app-ph": "Applied Physics",
        "physics.bio-ph": "Biological Physics",
        "physics.chem-ph": "Chemical Physics",
        "physics.comp-ph": "Computational Physics",
        "physics.data-an": "Data Analysis, Statistics and Probability",
        "physics.flu-dyn": "Fluid Dynamics",
        "physics.med-ph": "Medical Physics",
        "physics.optics": "Optics",
        "physics.soc-ph": "Physics and Society",
    }),
    "quant-ph": ("Quantum Physics", {}),
    "gr-qc": ("General Relativity and Quantum Cosmology", {}),
    "hep-th": ("High Energy Physics - Theory", {}),
    "hep-ph": ("High Energy Physics - Phenomenology", {}),
    "nlin": ("Nonlinear Sciences", {
        "nlin.AO": "Adaptation and Self-Organizing Systems",
        "nlin.CD": "Chaotic Dynamics",
        "nlin.PS": "Pattern Formation and Solitons",
    }),
}

# Syntactic check: archive (cs, q-bio, cond-mat) optionally followed by .SUB (CV, mtrl-sci).
_CODE_RE = re.compile(r"^[a-z]+(?:-[a-z]+)?(?:\.[A-Za-z]+(?:-[a-z]+)?)?$")


def is_valid_code(code: str) -> bool:
    return bool(_CODE_RE.match(code))


def is_domain(code: str) -> bool:
    """True for a whole archive (cs, math) rather than a single category (cs.CV)."""
    return "." not in code


def describe(code: str) -> str:
    """Human name for a domain or subdomain code, or '' if unknown."""
    if code in DOMAINS:
        return DOMAINS[code][0]
    dom = code.split(".", 1)[0]
    if dom in DOMAINS:
        return DOMAINS[dom][1].get(code, "")
    return ""


def format_listing() -> str:
    lines = []
    for dom, (name, subs) in DOMAINS.items():
        lines.append(f"{dom:<10} {name}")
        for code, sub in subs.items():
            lines.append(f"  {code:<22} {sub}")
    return "\n".join(lines)


# ---------------------------------------------------------------- interactive picker

def _ask(prompt: str, options: List[Tuple[str, str]], allow_all: Optional[str] = None) -> List[str]:
    """Numbered menu. Returns chosen codes. Accepts numbers ('3', '1,4') or raw codes ('cs.CV')."""
    for i, (code, name) in enumerate(options, 1):
        print(f"  {i:>3}. {code:<22} {name}")
    if allow_all:
        print(f"    0. (all of {allow_all})")
    while True:
        raw = input(f"{prompt}: ").strip()
        if not raw:
            continue
        picks: List[str] = []
        ok = True
        for tok in re.split(r"[,\s]+", raw):
            if tok.isdigit():
                n = int(tok)
                if n == 0 and allow_all:
                    picks.append(allow_all)
                elif 1 <= n <= len(options):
                    picks.append(options[n - 1][0])
                else:
                    ok = False
            elif is_valid_code(tok):
                picks.append(tok)
            else:
                ok = False
        if ok and picks:
            return picks
        print("  Not understood; enter numbers from the list (e.g. 3 or 1,4) or arXiv codes (e.g. cs.CV).")


def pick_categories() -> List[str]:
    print("\nDomains:")
    doms = _ask("Pick a domain", [(d, n) for d, (n, _) in DOMAINS.items()])
    if len(doms) != 1 or doms[0] not in DOMAINS or not DOMAINS[doms[0]][1]:
        return doms  # several domains, a raw code, or a domain without subdomains
    dom = doms[0]
    print(f"\n{DOMAINS[dom][0]} subdomains:")
    return _ask("Pick subdomain(s)", list(DOMAINS[dom][1].items()), allow_all=dom)


def pick_mode() -> Tuple[str, int]:
    print("\nMode:\n    1. today   (today's announcement feed)\n"
          "    2. recent  (the last N announcements, like arXiv's 'recent' page)")
    while True:
        raw = input("Pick a mode [1]: ").strip() or "1"
        if raw in ("1", "today"):
            return "today", 1
        if raw in ("2", "recent"):
            d = input("How many announcement days? [3]: ").strip() or "3"
            if d.isdigit() and int(d) > 0:
                return "recent", int(d)
        print("  Enter 1 or 2.")


def pick_keywords() -> List[str]:
    """Optional keyword filter. Quotes group a phrase: attention "vision transformer"."""
    raw = input("Keywords to filter by (Enter to skip): ").strip()
    try:
        return shlex.split(raw)
    except ValueError:  # unbalanced quote
        return raw.replace('"', " ").split()


def pick_to_save() -> Optional[Tuple[List[str], List[str]]]:
    """Ask which papers from the list to save, and with which tags. None when the user is done."""
    while True:
        raw = input("\nSave papers? Type their numbers (e.g. 3 7 12), or press Enter to finish: ").strip()
        if not raw:
            return None
        numbers = re.split(r"[,\s]+", raw)
        if all(n.isdigit() for n in numbers):
            break
        print("  Numbers from the list only, e.g. 3 7 12.")
    tags = input("Tags for them (e.g. important to-read; Enter for none): ").strip()
    return numbers, [t for t in re.split(r"[,\s]+", tags) if t]
