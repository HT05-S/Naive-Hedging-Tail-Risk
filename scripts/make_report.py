"""Write the final report, as a Word document or as a PDF typeset with LaTeX.

    python scripts/make_report.py            # Word:  <name>.docx, at the top level of the repository
    python scripts/make_report.py --latex    # PDF:   <name>.pdf at the top level; LaTeX source in report/ (needs latexmk)

Both versions are produced from the same text and the same numbers below.

Every number in the tables, and every number in the text that depends on our results, is read from
results/tables/ (written by scripts/make_tables.py). Figures come from results/figures/.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hedging import analysis, data  # noqa: E402
from hedging.evaluate import COST_PER_TRADE, RISK_AVERSION  # noqa: E402
from hedging.models import MODELS  # noqa: E402
from hedging.report_tables import (COL_LABELS, COLS, H1, H2, PAPER_NAIVE, PAPER_NAIVE_WINS, PAPER_NAIVE_WINS_IS,  # noqa: E402
                                   PAPER_OLS_VAR_HE, PAPER_SEMI, Results, fmt, label)

LATEX = "--latex" in sys.argv
OUT = ROOT / "FRE6123_Final_Report_Tomar_Dhanasekaran_Kishore.docx"       # the PDF is written next to it
TEX_DIR = ROOT / "report"                                                # LaTeX source and build files
FIG = data.RESULTS / "figures"
FONT = "Times New Roman"
L = data.LABELS
R = Results()

# ------------------------------------------------------------------ document helpers

doc = Document()
sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
for side in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
    setattr(sec, side, Inches(1))


def set_font(run, size=11, bold=None, italic=None):
    run.font.name = FONT
    run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    run.font.size = Pt(size)
    run.font.color.rgb = RGBColor(0, 0, 0)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic


def plain(text):
    """Word version of a string: each math span ⟦latex‖plain text⟧ is replaced by its plain-text half."""
    return re.sub(r"⟦.*?‖(.*?)⟧", r"\1", str(text))


def add_runs(par, text, size=11, bold=False):
    """Text with **bold** and *italic* spans."""
    for part in re.split(r"(\*\*.+?\*\*|\*.+?\*)", plain(text)):
        if not part:
            continue
        if part.startswith("**"):
            set_font(par.add_run(part[2:-2]), size, True)
        elif part.startswith("*"):
            set_font(par.add_run(part[1:-1]), size, bold, True)
        else:
            set_font(par.add_run(part), size, bold)


def para(text, size=11, align=WD_ALIGN_PARAGRAPH.JUSTIFY, after=6, before=0, indent=None, keep=False):
    p = doc.add_paragraph()
    p.alignment = align
    f = p.paragraph_format
    f.space_after, f.space_before, f.line_spacing = Pt(after), Pt(before), 1.08
    if indent:
        f.left_indent = Inches(indent)
    f.keep_with_next = keep
    add_runs(p, text, size)
    return p


def heading(text, level=1):
    p = doc.add_paragraph()
    f = p.paragraph_format
    f.space_before, f.space_after, f.keep_with_next = Pt(12 if level == 1 else 8), Pt(4), True
    set_font(p.add_run(text), 13 if level == 1 else 11.5, True, level == 2)
    return p


def shade(cell, color):
    tc = cell._element.get_or_add_tcPr()
    s = OxmlElement("w:shd")
    s.set(qn("w:val"), "clear"), s.set(qn("w:color"), "auto"), s.set(qn("w:fill"), color)
    tc.append(s)


def borders(table):
    """Rules above and below the header and below the last row only."""
    tbl = table._element
    pr = tbl.tblPr
    b = OxmlElement("w:tblBorders")
    for edge in ("top", "bottom"):
        e = OxmlElement(f"w:{edge}")
        e.set(qn("w:val"), "single"), e.set(qn("w:sz"), "8"), e.set(qn("w:color"), "000000")
        b.append(e)
    pr.append(b)
    for cell in table.rows[0].cells:
        tc = cell._element.get_or_add_tcPr()
        tb = OxmlElement("w:tcBorders")
        e = OxmlElement("w:bottom")
        e.set(qn("w:val"), "single"), e.set(qn("w:sz"), "6"), e.set(qn("w:color"), "000000")
        tb.append(e)
        tc.append(tb)


N_TABLE = [0]
N_FIG = [0]
N_EQ = [0]
TABLE_PLACE = ["!htb"]        # LaTeX placement of tables: floating in the main text, fixed ("H") in the appendices


def equation(latex, text):
    """A numbered display equation. Word shows the plain-text form; the PDF typesets the LaTeX form."""
    N_EQ[0] += 1
    para(f"{text}        ({N_EQ[0]})", 11, WD_ALIGN_PARAGRAPH.CENTER, after=6)


def latex_only(block, word_text=None):
    """A block that exists only in the PDF (the mathematical appendix). Word gets a one-line pointer."""
    if word_text:
        para(word_text, 10)


def table(title, header, rows, widths, size=9, note=None, bold=None, group_rows=()):
    """`rows` is a list of lists of strings. `bold` is a set of (row, col). `group_rows` are full-width label rows."""
    N_TABLE[0] += 1
    cap = para(f"**Table {N_TABLE[0]}.** {title}", 10, WD_ALIGN_PARAGRAPH.LEFT, after=3, before=6, keep=True)
    t = doc.add_table(rows=1 + len(rows), cols=len(header))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    bold = bold or set()
    for i, line in enumerate([header] + rows):
        for j, text in enumerate(line):
            c = t.cell(i, j)
            c.width = Inches(widths[j])
            p = c.paragraphs[0]
            p.paragraph_format.space_after = p.paragraph_format.space_before = Pt(1)
            p.alignment = WD_ALIGN_PARAGRAPH.LEFT if j == 0 else WD_ALIGN_PARAGRAPH.CENTER
            is_group = (i - 1) in group_rows
            set_font(p.add_run(plain(text)), size, bold=(i == 0) or is_group or ((i - 1, j) in bold), italic=is_group)
            if i < len(rows):
                p.paragraph_format.keep_with_next = True
        if (i - 1) in group_rows:
            m = t.cell(i, 0).merge(t.cell(i, len(header) - 1))
            for extra in m.paragraphs[1:]:                      # merging keeps one empty paragraph per merged cell
                extra._element.getparent().remove(extra._element)
            shade(m, "F2F2F2")
    borders(t)
    if note:
        para(f"*Note.* {note}", 8.5, WD_ALIGN_PARAGRAPH.LEFT, after=8, before=2)
    else:
        para("", 4, after=2)
    return cap


def figure(name, caption, width=6.3):
    N_FIG[0] += 1
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.add_run().add_picture(str(FIG / name), width=Inches(width))
    para(f"**Figure {N_FIG[0]}.** {caption}", 10, WD_ALIGN_PARAGRAPH.LEFT, after=8)


def page_number_footer():
    p = sec.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run()
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        if kind:
            e = OxmlElement("w:fldChar")
            e.set(qn("w:fldCharType"), kind)
        else:
            e = OxmlElement("w:instrText")
            e.set(qn("xml:space"), "preserve")
            e.text = text
        run._element.append(e)
    set_font(run, 9)


def title_block(title, subtitle, authors, lines):
    para(title, 17, WD_ALIGN_PARAGRAPH.CENTER, after=2).runs[0].bold = True
    para(subtitle, 13, WD_ALIGN_PARAGRAPH.CENTER, after=10)
    para(authors, 11.5, WD_ALIGN_PARAGRAPH.CENTER, after=2)
    for i, line in enumerate(lines):
        para(line, 10.5, WD_ALIGN_PARAGRAPH.CENTER, after=12 if i == len(lines) - 1 else 2)


def reference(text):
    p = para(text, 10, WD_ALIGN_PARAGRAPH.LEFT, after=3)
    p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Inches(0.3), Inches(-0.3)


def page_break():
    doc.add_page_break()


def finish():
    page_number_footer()
    doc.save(OUT)
    print("report ->", OUT)


# ------------------------------------------------------------------ LaTeX versions of the same helpers

TEX: list[str] = []
ESCAPES = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_", "{": r"\{",
           "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
PREAMBLE = r"""\documentclass[11pt,letterpaper]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{amsmath}
\usepackage{newtxtext,newtxmath}
\usepackage[margin=1in]{geometry}
\usepackage{microtype,parskip,graphicx,booktabs,array,float,caption,titlesec,textcomp}
\PassOptionsToPackage{hyphens}{url}
\usepackage[hidelinks]{hyperref}
\urlstyle{same}
\DeclareUnicodeCharacter{2212}{\textminus}
\captionsetup{font=small,labelfont=bf,labelsep=period,justification=raggedright,singlelinecheck=false,skip=4pt}
\titleformat*{\section}{\large\bfseries}
\titleformat*{\subsection}{\normalsize\bfseries\itshape}
\titlespacing*{\section}{0pt}{14pt}{4pt}
\titlespacing*{\subsection}{0pt}{10pt}{2pt}
\hypersetup{pdftitle={Is the Naive Hedge Still Hard to Beat?},pdfauthor={Hina Tomar, Kavin Dhanasekaran, Sai Kishore}}
\raggedbottom
\widowpenalty=10000
\clubpenalty=10000
\emergencystretch=1em
\begin{document}
"""


def tex(text: str) -> str:
    """Escape LaTeX characters, turn **bold** and *italic* spans into commands, and typeset ⟦latex‖plain⟧ math spans."""
    out = []
    for part in re.split(r"(⟦.*?⟧|\*\*.+?\*\*|\*.+?\*)", str(text)):
        if part.startswith("⟦"):
            out.append("$" + part[1:-1].split("‖")[0] + "$")
        elif part.startswith("**") and len(part) > 4:
            out.append(r"\textbf{" + tex(part[2:-2]) + "}")
        elif part.startswith("*") and len(part) > 2:
            out.append(r"\textit{" + "".join(ESCAPES.get(c, c) for c in part[1:-1]) + "}")
        else:
            out.append("".join(ESCAPES.get(c, c) for c in part))
    return "".join(out)


if LATEX:
    def para(text, size=11, align=None, after=6, before=0, indent=None, keep=False):          # noqa: F811
        body = tex(text)
        if size <= 10:
            body = r"{\small " + body + r"\par}"
        TEX.append(r"\begin{quote}" + "\n" + body + "\n" + r"\end{quote}" if indent else body)
        TEX.append("")

    def heading(text, level=1):                                                               # noqa: F811
        TEX.append((r"\section*{" if level == 1 else r"\subsection*{") + tex(text) + "}\n")

    def equation(latex, text):                                                                # noqa: F811
        N_EQ[0] += 1
        TEX.append(r"\begin{equation}" + "\n" + latex + "\n" + r"\end{equation}" + "\n")

    def latex_only(block, word_text=None):                                                    # noqa: F811
        TEX.append(block + "\n")

    def table(title, header, rows, widths, size=9, note=None, bold=None, group_rows=()):      # noqa: F811
        N_TABLE[0] += 1
        bold, n, total = bold or set(), len(header), sum(widths)
        spec = "@{}" + "".join(
            (r">{\raggedright\arraybackslash}" if j == 0 else r">{\centering\arraybackslash}")
            + rf"p{{\dimexpr {w / total:.4f}\linewidth-2\tabcolsep\relax}}" for j, w in enumerate(widths)) + "@{}"
        lines = [r"\begin{table}[" + TABLE_PLACE[0] + "]", rf"\caption{{{tex(title)}}}", r"\centering",
                 rf"\fontsize{{{size}}}{{{size * 1.25:.1f}}}\selectfont\setlength{{\tabcolsep}}{{3pt}}",
                 rf"\begin{{tabular}}{{{spec}}}", r"\toprule",
                 " & ".join(rf"\textbf{{{tex(h)}}}" if h else "" for h in header) + r" \\", r"\midrule"]
        for i, row in enumerate(rows):
            if i in group_rows:
                lines.append((r"\addlinespace[3pt]" if i else "")
                             + rf"\multicolumn{{{n}}}{{@{{}}l}}{{\textbf{{\textit{{{tex(row[0])}}}}}}} \\")
            else:
                cells = [re.sub(r"(?<![\w.])-(?=\d)", "−", str(c)) for c in row]          # true minus signs
                lines.append(" & ".join(rf"\textbf{{{tex(c)}}}" if (i, j) in bold else tex(c)
                                        for j, c in enumerate(cells)) + r" \\")
        lines += [r"\bottomrule", r"\end{tabular}"]
        if note:
            lines.append(r"\par\vspace{3pt}\begin{minipage}{\linewidth}\footnotesize\raggedright \textit{Note.} "
                         + tex(note) + r"\end{minipage}")
        TEX.append("\n".join(lines + [r"\end{table}", ""]))

    def figure(name, caption, width=6.3):                                                     # noqa: F811
        N_FIG[0] += 1
        TEX.append("\n".join([r"\begin{figure}[!htb]", r"\centering",
                              rf"\includegraphics[width={min(width, 6.5)}in]{{../results/figures/{name}}}",
                              rf"\caption{{{tex(caption)}}}", r"\end{figure}", ""]))

    def title_block(title, subtitle, authors, lines):                                         # noqa: F811
        TEX.append("\n".join([r"\begin{center}", rf"{{\LARGE\bfseries {tex(title)}\par}}\vspace{{4pt}}",
                              rf"{{\large {tex(subtitle)}\par}}\vspace{{10pt}}", rf"{{{tex(authors)}\par}}\vspace{{2pt}}"]
                             + [rf"{{\small {tex(x)}\par}}" for x in lines] + [r"\end{center}", ""]))

    def reference(text):                                                                      # noqa: F811
        body = "".join(r"\url{" + part + "}" if part.startswith("https://") else tex(part)
                       for part in re.split(r"(https://\S+)", text))
        TEX.append(r"{\small\setlength{\parskip}{0pt}\interlinepenalty=10000\hangindent=0.3in\hangafter=1\noindent " + body + r"\par}" + "\n")

    def page_break():                                                                         # noqa: F811
        TEX.append(r"\clearpage" + "\n")

    def finish():                                                                             # noqa: F811
        TEX_DIR.mkdir(exist_ok=True)
        out = TEX_DIR / OUT.with_suffix(".tex").name
        out.write_text(PREAMBLE + "\n".join(TEX) + "\n\\end{document}\n", encoding="utf-8")
        print("report ->", out)
        if shutil.which("latexmk") is None:
            print("latexmk not found: compile the .tex file with pdflatex to get the PDF")
            return
        run = subprocess.run(["latexmk", "-pdf", "-interaction=nonstopmode", "-halt-on-error", "-outdir=build", out.name],
                             cwd=out.parent, capture_output=True, text=True)
        if run.returncode != 0:
            print(run.stdout[-3000:])
            raise SystemExit("LaTeX failed; see report/build/*.log")
        shutil.copy(TEX_DIR / "build" / out.with_suffix(".pdf").name, OUT.with_suffix(".pdf"))
        print("report ->", OUT.with_suffix(".pdf"))


# ------------------------------------------------------------------ numbers used in the text

A = {m: R.scorecard_row("paper", m, "original") for m in H1}          # replication
B = {m: R.scorecard_row("ours", m, "original") for m in H1}           # same period, our setting
C = {m: R.scorecard_row("ours", m, "post") for m in H1}               # extension, our setting
CP = {m: R.scorecard_row("paper", m, "post") for m in H1}             # extension, paper setting
F = {m: R.scorecard_row("ours", m, "full") for m in H1 + H2}          # full sample, our setting
D = {m: F[m] for m in H2}
NGF = R.scorecard_row("ours", "NATGAS", "full", "fred_only")
XBT = R.scorecard_row("ours_xbt", "BTC", "full")
A_IS = {m: int(R.wins("paper", m, "original", mode="is")["naive"]) for m in H1}
D_IS = {m: int(R.wins("ours", m, "full", mode="is")["naive"]) for m in H2}
naive = {m: R.grid("paper", m, "original").loc["naive"] for m in H1}
diff = {m: np.abs(naive[m].to_numpy() - np.array(PAPER_NAIVE[m])) for m in H1}
tot = lambda d, k: sum(v[k] for v in d.values())                      # noqa: E731
ng, btc = R.grid("ours", "NATGAS", "full"), R.grid("ours", "BTC", "full")
ng_var = R.grid("ours", "NATGAS", "full", val="he_var")
btc_x = R.grid("ours_xbt", "BTC", "full")
sp_post_ours, sp_post_paper = R.grid("ours", "SP500", "post"), R.grid("paper", "SP500", "post")
ratio = R.ratios[(R.ratios.side == "down") & (R.ratios.measure == "CVaR")]
sd = lambda st, m, model: float(ratio[(ratio.setting == st) & (ratio.market == m) & (ratio.model == model)]["sd"].iloc[0])  # noqa: E731
mean_b = lambda st, m, model: float(ratio[(ratio.setting == st) & (ratio.market == m) & (ratio.model == model)]["mean"].iloc[0])  # noqa: E731
MAIN = [("paper", m, "original") for m in H1] + [("ours", m, "full") for m in H2]


def distinct_tests(setting, market, sample):
    """Tests of an estimated model against the naive hedge that are not repeats.

    The OLS and semivariance ratios are the same for VaR and CVaR, and the test compares the same quantile of the same
    two series, so their CVaR tests repeat their VaR tests. Returns (number of distinct tests, number of them in which
    the paired test finds the naive hedge better at the 5% level).
    """
    x = R.cell(setting, market, sample)
    x = x[(x.model != "naive") & ~(x.model.isin(["ols", "sv"]) & (x.measure == "CVaR"))]
    return len(x), int((x.p_paired > 0.95).sum())


def near_ties(setting, market, sample, tol=0.005):
    """Scenarios (of 12) in which the naive hedge and the best estimated model are within tol in effectiveness."""
    g = R.grid(setting, market, sample)
    return int(((g.loc["naive"] - g.drop("naive").max()).abs() < tol).sum())


DIST_A = [distinct_tests("paper", m, "original") for m in H1]
N_DIST, N_DIST_PAIR95 = sum(a for a, _ in DIST_A), sum(b for _, b in DIST_A)


def is_gain(st, m, sm):
    """Mean over scenarios of (best estimated model in-sample) minus (best estimated model out-of-sample)."""
    o, i = R.grid(st, m, sm).drop("naive").max(), R.grid(st, m, sm, mode="is").drop("naive").max()
    return float((i - o).mean())


def is_lead(st, m, sm):
    """Mean over scenarios of (best estimated model in-sample) minus (naive hedge in-sample)."""
    g = R.grid(st, m, sm, mode="is")
    return float((g.drop("naive").max() - g.loc["naive"]).mean())


def utility_before_costs(st, m, sm):
    """Naive minus model mean-variance utility with no transaction costs, averaged over the 12 scenarios."""
    d, B = analysis.aligned(st, m, "oos")
    keep = (d["target_wed"] <= data.ORIGINAL_END).to_numpy() if sm == "original" else np.ones(len(d), dtype=bool)
    s, f = d["s"].to_numpy()[keep], d["f"].to_numpy()[keep]
    u = lambda y: y.mean() - 0.5 * RISK_AVERSION * y.var(ddof=1)          # noqa: E731
    return {k: float(np.mean([u(s - f) - u(s - B[(k,) + c].to_numpy()[keep] * f) for c in COLS])) for k in MODELS if k != "naive"}


def at_limit(st, m):
    """Share of Cornish-Fisher hedge ratios at either end of the search grid."""
    b = analysis.load_ratios(st, m)["cfe"].to_numpy()
    return float(((b == 0.0) | (b == 2.0)).mean())


weekly = pd.read_csv(data.PROCESSED / "weekly_market_returns.csv", parse_dates=["target_wed"], low_memory=False)


def roll_gap(market, after=None):
    """Spliced minus same-contract futures return in roll weeks (log points)."""
    g = weekly[weekly.market == market].sort_values("target_wed").reset_index(drop=True)
    gap = np.log(g.fut_price_prev / g.fut_price.shift(1))
    m = g.roll_at_interval_start.astype(bool) & g.return_defined & g.return_defined.shift(1, fill_value=False) & gap.notna()
    if after is not None:
        m &= g.target_wed > after
    return gap[m]


gap_ng, gap_sp_post = roll_gap("NATGAS"), roll_gap("SP500", data.ORIGINAL_END)
uri = weekly[(weekly.market == "NATGAS") & (weekly.target_wed.isin(pd.to_datetime(["2021-02-10", "2021-02-17", "2021-02-24"])))].set_index("target_wed")

# bias of the naive hedge against the noise of the estimated ratios (Table 8); natural gas without Winter Storm Uri
BN = pd.read_csv(data.RESULTS / "tables" / "bias_noise.csv").set_index("market")
NGU = pd.read_csv(data.RESULTS / "tables" / "natgas_without_uri.csv").set_index("sample")
NOT_NG = [m for m in BN.index if m != "NATGAS"]
ols_mult = {m: BN.loc[m, "noise_ols"] / BN.loc[m, "bias"] for m in NOT_NG}
hs_mult = {m: BN.loc[m, "noise_hs"] / BN.loc[m, "bias"] for m in NOT_NG}
cfe_noisier = int((BN.noise_cfe > BN.noise_hs).sum())
assert [m for m in NOT_NG if ols_mult[m] < 1] == ["BTC"] and BN.loc["NATGAS", "noise_ols"] > BN.loc["NATGAS", "noise_hs"]
se_ols = lambda m, n=52: float(np.sqrt(BN.loc[m, "beta"] ** 2 / n * (1 - BN.loc[m, "r2"]) / BN.loc[m, "r2"]))  # noqa: E731


def series(st, m, sm):
    """Spot returns, futures returns and out-of-sample ratios on the evaluation weeks of a sample."""
    d, B = analysis.aligned(st, m, "oos")
    keep = (d["target_wed"] <= data.ORIGINAL_END).to_numpy() if sm == "original" else np.ones(len(d), dtype=bool)
    return d["s"].to_numpy()[keep], d["f"].to_numpy()[keep], B[keep]


def corr_with_naive():
    """Correlation of each model's hedged returns with the naive hedge's, over markets, models and scenarios."""
    out = []
    for st, m, sm in MAIN:
        s_, f_, B_ = series(st, m, sm)
        out += [np.corrcoef(s_ - f_, s_ - B_[(k,) + c].to_numpy() * f_)[0, 1] for k in MODELS if k != "naive" for c in COLS]
    return np.array(out)


CORR = corr_with_naive()


def cvar5(x):
    return -x[x <= np.quantile(x, 0.05)].mean()


s_w, f_w, B_w = series("paper", "WTI", "original")
loss_unhedged, loss_naive = (1 - np.exp(-cvar5(s_w))) * 100, (1 - np.exp(-cvar5(s_w - f_w))) * 100   # $ million per $100 million
b_hs = B_w[("hs", "down", "CVaR", 0.05)].to_numpy()
hs_cost = COST_PER_TRADE * np.abs(np.diff(b_hs)).sum()
hs_var_gap = 0.5 * RISK_AVERSION * ((s_w - b_hs * f_w).var(ddof=1) - (s_w - f_w).var(ddof=1))


def distinct_frame(setting, market, sample):
    x = R.cell(setting, market, sample)
    return x[(x.model != "naive") & ~(x.model.isin(["ols", "sv"]) & (x.measure == "CVaR"))]


DA = pd.concat([distinct_frame("paper", m, "original") for m in H1])
P_MIN, P_MED = float(DA.p_wilcox.min()), float(DA.p_wilcox.median())
N_PAIR05, N_NO_RESAMPLE = int((DA.p_paired < 0.05).sum()), int((DA.p_paired == 1).sum())
sp_flags_distinct = int((distinct_frame("ours", "SP500", "post").p_paired < 0.05).sum())
sp_full = R.grid("ours", "SP500", "full")
sp_full_margin = float((sp_full.drop("naive").max() - sp_full.loc["naive"]).max())
sp_post_margin = float((sp_post_ours.drop("naive").max() - sp_post_ours.loc["naive"]).max())
N_NOCOP, N_NOCOP_PAIR95 = int((DA.model != "copula").sum()), int((DA[DA.model != "copula"].p_paired > 0.95).sum())
IS_AHEAD = {k: sum(int((R.grid(st, m, sm, mode="is").loc[k] > R.grid(st, m, sm, mode="is").loc["naive"]).sum()) for st, m, sm in MAIN)
            for k in MODELS if k != "naive"}                        # market-scenario pairs (of 72) in which the model beats naive in-sample
assert IS_AHEAD["sv"] > IS_AHEAD["hs"] > IS_AHEAD["ols"] > 36 > IS_AHEAD["cfe"] > IS_AHEAD["copula"]
VAR = {m: R.grid(st, m, sm, val="he_var").iloc[:, 0] for st, m, sm in MAIN}                    # variance removed, by model
SEMI = {m: R.grid(st, m, sm, val="he_sv")[("down", "VaR", 0.05)] for st, m, sm in MAIN}        # downside semivariance removed
var_naive_ahead = [m for m in VAR if VAR[m]["naive"] >= VAR[m]["ols"]]
assert [m for m in VAR if m not in var_naive_ahead] == ["SP500"] and abs(VAR["SP500"]["ols"] - VAR["SP500"]["naive"]) < 0.0001
semi_best = {m: SEMI[m][["naive", "ols", "sv"]].idxmax() for m in SEMI}
semi_gap = max(float(SEMI[m][["ols", "sv"]].max() - SEMI[m]["naive"]) for m in SEMI)
se2 = lambda m: se_ols(m) ** 2 * 100                                                            # noqa: E731
cop4 = float(np.mean([mean_b("paper", m, "copula") for m in H1]))
cop2 = float(np.mean([mean_b("ours", m, "copula") for m in H2]))
assert all(max(PAPER_SEMI[m], key=PAPER_SEMI[m].get) == semi_best[m] for m in H1)             # same ordering as the paper's Table 6
d_ai, _ = analysis.aligned("ours", "SP500", "oos")
d_ai = d_ai[d_ai["target_wed"] >= "2023-07-05"]
sx_ai = np.log(pd.read_csv(data.RAW / "bloomberg" / "SOXX_US_Equity.csv", parse_dates=["date"]).set_index("date")
               ["TOT_RETURN_INDEX_GROSS_DVDS"].reindex(d_ai.index)).diff()
assert sx_ai[(d_ai["target_wed"] == "2025-01-29").to_numpy()].iloc[0] <= sx_ai.quantile(0.10)     # the DeepSeek week is flagged
d_sp, _ = analysis.aligned("ours", "SP500", "oos")
post_sp = (d_sp["target_wed"] > data.ORIGINAL_END).to_numpy()
sp_hedged_sd_post, sp_hedged_sd_pre = (d_sp["s"] - d_sp["f"])[post_sp].std(), (d_sp["s"] - d_sp["f"])[~post_sp].std()
TAIL3 = DA[DA.model.isin(["hs", "cfe", "copula"])]
OLSSV = DA[DA.model.isin(["ols", "sv"])]
N_TAIL3, N_TAIL3_PAIR95 = len(TAIL3), int((TAIL3.p_paired > 0.95).sum())
N_OLSSV, N_OLSSV_PAIR95 = len(OLSSV), int((OLSSV.p_paired > 0.95).sum())
assert N_TAIL3_PAIR95 > N_TAIL3 / 2 and N_OLSSV_PAIR95 < N_OLSSV / 2
assert BN.beta.idxmin() == "BTC" and BN.beta.idxmax() == "NATGAS"          # Bitcoin's best ratio is furthest from one
lead_over_ols = {m: float((R.grid(st, m, sm).loc["naive"] - R.grid(st, m, sm).loc["ols"]).mean()) for st, m, sm in MAIN}
assert max(lead_over_ols, key=lead_over_ols.get) == "NATGAS"

# ------------------------------------------------------------------ title and abstract

title_block("Is the Naïve Hedge Still Hard to Beat?",
            "Tail-Risk Hedging with Futures, 1990–2026, with Evidence from Bitcoin and Natural Gas",
            "Hina Tomar, Kavin Dhanasekaran and Sai Kishore",
            ["FRE 6123 Financial Risk Management, Fall 2026 · Group Project: Final Report",
             "Department of Finance and Risk Engineering, NYU Tandon School of Engineering",
             "November 13, 2026"])

heading("Abstract")
para(
    "Cao and Conlon (2025) report that a one-for-one futures hedge reduces tail risk at least as well as five estimated "
    "hedge-ratio models in four markets between 1990 and June 2023. We rebuild their study from raw Bloomberg and FRED "
    "data with our own code and ask two questions: does the result survive an independent replication and three further "
    "years of data, and does it extend to Bitcoin and natural gas, two markets with fatter tails and a less stable link "
    "between spot and futures prices? It does. In the original sample the naïve hedge is the most effective model in "
    f"{A['WTI']['naive']}, {A['GBPUSD']['naive']}, {A['SP500']['naive']} and {A['GOLD']['naive']} of 12 tail-risk "
    "scenarios for WTI crude oil, GBP/USD, the S&P 500 and gold, and no estimated model beats it at the 10% significance "
    f"level in any of {60 * 4} tests of tail quantiles ({N_DIST} of them distinct). The same test favors no estimated model from July 2023 "
    "to November 2026 or in Bitcoin and natural gas. The S&P 500 is the one exception to the pattern of wins: there all "
    "models are near-ties, the OLS hedge wins more scenarios than the naïve hedge once the new weeks are added, and "
    "after June 2023 the paired test described next favors two estimated models, by margins below 0.01. A "
    "paired version of the paper's test, which we add because it has more power, strengthens the conclusion: the "
    f"naïve hedge is significantly better than the estimated model in {N_DIST_PAIR95} of the {N_DIST} distinct "
    f"original-sample comparisons ({N_NOCOP_PAIR95} of {N_NOCOP} without the copula model, which is misspecified). The evidence is consistent with estimation error as the "
    "reason. The best hedge ratio is close to one in every market, so the bias of a fixed ratio is small, while ratios "
    "fitted to the tail of a year of data are many times noisier. Estimated hedge ratios move widely from week to "
    "week, they win in-sample and lose out-of-sample, and the naïve hedge's lead is widest in natural gas, where "
    "the spot–futures relation is least stable. Each of these is a prediction of the estimation-error explanation that "
    "the data could have contradicted. One further check failed narrowly, in Bitcoin, and the rest held. The evidence is "
    "for a 52-week estimation window only."
)

# ------------------------------------------------------------------ 1 introduction

heading("1. Introduction")
para(
    "The simplest futures hedge sells one unit of futures for each unit of the asset held. It needs no data and no "
    "model. Decades of research have tried to improve on it, and a recent study finds that, for the large losses that "
    "risk managers care most about, none of the improvements works reliably (Cao & Conlon, 2025). This report tests "
    "that claim and extends it."
)
para(
    "A firm that holds oil, a foreign currency or an equity portfolio can remove most of its price risk by selling "
    "futures. The first decision is how many futures to sell for each unit held: the hedge ratio. The textbook answer is "
    "the ratio that minimizes the variance of the hedged position, estimated by regressing spot returns on futures "
    "returns (Ederington, 1979). Risk managers and regulators, however, care most about large losses. The Basel market "
    "risk framework measures capital with expected shortfall, a tail measure (Basel Committee on Banking Supervision, "
    "2019), and a large literature has proposed hedge ratios that minimize Value-at-Risk (VaR) or Conditional "
    "Value-at-Risk (CVaR) directly (Harris & Shen, 2006; Cao et al., 2010)."
)
para(
    "Cao and Conlon (2025) challenge the value of that effort. Using weekly data for WTI crude oil, GBP/USD, the S&P 500 "
    "and gold from January 1990 to June 2023, they compare six ways of setting the hedge ratio and find that none of the "
    "five estimated models reduces tail risk significantly more than the simplest rule, one unit of futures per unit of "
    "spot. The claim is uncomfortable for quantitative risk management. If it is right, estimating a hedge ratio adds "
    "cost and model risk without adding protection. It is also debatable: the result rests on one sample, four mature "
    "markets and one set of data-handling choices that the paper does not fully describe."
)
para(
    "The question is timely for two reasons. First, the paper's sample ends in June 2023. Since then markets have been "
    "through the yen carry-trade unwind of August 2024 (Aquilina et al., 2024) and the tariff sell-off of April 2025 "
    "(International Monetary Fund, 2025). Second, two markets that are now widely hedged with futures were not in the "
    "study. Bitcoin futures have traded on the CME since December 2017, and U.S. spot Bitcoin exchange-traded products "
    "were approved in January 2024 (Gensler, 2024). Natural gas is exposed to weather shocks such as Winter Storm Uri in "
    "February 2021 (FERC & NERC, 2021). Both have fatter tails than the paper's four markets and a looser link between "
    "spot and futures prices, which is where a fixed one-for-one hedge should be most at risk."
)
para(
    "This report asks whether the naïve hedge remains difficult to beat in reducing tail risk through 2026, and whether "
    "that conclusion extends to Bitcoin and natural gas. We rebuild the study from raw data with our own code, reproduce "
    "its central result, and then extend it in time and across markets. Our thesis has two parts. The first is "
    "that the naïve hedge remains hard to beat. The second is that the results follow the pattern that estimation "
    "error predicts for three of the five estimated models, and not the pattern that basis risk would produce: "
    "estimated ratios are unstable, they win in-sample and lose out-of-sample, and an unstable spot–futures relation "
    "does not rescue them. The other two models, the copula and in part the Cornish–Fisher hedge, also suffer from their "
    "own design (Section 6). "
    "We test these predictions with the paper's 52-week window; other window lengths are outside our scope (Section 6)."
)
para(
    "We report four main findings. First, the paper's central result replicates: between 1990 and June 2023 no estimated "
    f"model beats the naïve hedge at the 10% level in any of the {60 * 4} tests, and a paired version of the test finds the "
    f"naïve hedge significantly better in {N_DIST_PAIR95} of the {N_DIST} distinct comparisons. Second, the test result "
    "persists from July 2023 to November 2026 and extends to Bitcoin and natural gas, with one qualification: in the "
    "S&P 500 all models are near-ties and the naïve hedge does not win the most scenarios. Third, the evidence is "
    "consistent with estimation error as the cause. The variance-minimizing hedge ratio lies between "
    f"{BN.beta.min():.2f} and {BN.beta.max():.2f} in every market, so fixing it at one costs little, while the variance of "
    f"a ratio fitted to the tail of one year of data is {min(hs_mult.values()):.0f} to {max(hs_mult.values()):.0f} times "
    "that cost in five of the six markets, and far more in natural gas. Fourth, basis risk does not rescue the estimated "
    "models: the naïve hedge's lead in effectiveness is widest in natural gas, the market with the loosest link between "
    "spot and futures prices. The evidence from Bitcoin, where the best ratio is furthest from one, is weaker."
)
para(
    "Section 2 reviews the literature and states the hypotheses. Sections 3 and 4 describe the data and the method. "
    "Section 5 reports the results, Section 6 discusses alternative interpretations and limitations, and Section 7 concludes."
)

# ------------------------------------------------------------------ 2 background

heading("2. Background and Hypotheses")
heading("2.1 Related literature", 2)
para(
    "Ederington (1979) defined hedging effectiveness as the share of spot variance removed by the hedge and showed that "
    "the variance-minimizing ratio is the slope of a regression of spot on futures returns. Later work replaced variance "
    "with measures of downside risk. Harris and Shen (2006) choose the ratio that minimizes historical-simulation VaR or "
    "CVaR. Cao et al. (2010) use a Cornish–Fisher expansion, which needs less data because it uses the skewness and "
    "kurtosis of the whole distribution, not only its tail. Cotter and Hanly (2006) and Conlon and Cotter (2013) evaluate "
    "hedges by the reduction in VaR, CVaR and semivariance."
)
para(
    "A second literature doubts that estimated ratios help out of sample. DeMiguel et al. (2009) show that an equally "
    "weighted portfolio is rarely beaten by optimized portfolios because the inputs to the optimization are estimated "
    "with error, and that the estimation window needed for the optimized portfolio to win is far longer than the data "
    "usually available. Wang et al. (2015) carry the argument to futures hedging: across 24 markets, no minimum-variance model "
    "consistently beats the naïve hedge out of sample. Cao and Conlon (2025) extend this to tail risk. In their Table 5 "
    f"the naïve hedge is the most effective model in {PAPER_NAIVE_WINS['WTI']} of 12 scenarios for WTI, "
    f"{PAPER_NAIVE_WINS['GBPUSD']} for GBP/USD, {PAPER_NAIVE_WINS['SP500']} for the S&P 500 and "
    f"{PAPER_NAIVE_WINS['GOLD']} for gold, and most p-values for the alternatives are above 0.5. In-sample, when the "
    f"ratio is estimated on the same weeks it is evaluated on, the naïve hedge is best in only "
    f"{PAPER_NAIVE_WINS_IS['WTI']} of 12 scenarios for WTI and {PAPER_NAIVE_WINS_IS['GBPUSD']} for each of the others."
)
heading("2.2 Hypotheses", 2)
para("**H1 (Replication and persistence).** For WTI crude oil, GBP/USD, the S&P 500 and gold, no estimated hedge-ratio "
     "model significantly and consistently outperforms the naïve hedge in reducing VaR, CVaR or semivariance, in the "
     "original sample (January 1990 to June 2023) or in the extension to November 2026.", indent=0.3)
para("**H2 (Generalization to new markets).** The same holds for Bitcoin (2017–2026) and natural gas (1999–2026), "
     "despite their fat tails and unstable basis.", indent=0.3)
heading("2.3 Argument and counterargument", 2)
para(
    "The argument for both hypotheses is estimation error. A 52-week window holds five or six observations in its worst "
    "10% and a single one in its worst 1%, so a ratio fitted to the tail is fitted to a handful of weeks and will not "
    "carry over to the next week. The naïve ratio is not estimated and has no such error. If this is right, three things "
    "should be visible in the data: estimated ratios should vary widely over time, estimated models should win when "
    "evaluated in-sample, and their advantage should disappear out of sample."
)
para(
    "The paper offers estimation error as its explanation without formalizing it. A simple decomposition, which we add, "
    "makes the argument precise. Take variance as the measure of risk, where the algebra is "
    "exact. The hedged return ⟦y = s - b f‖y = s − b·f⟧ has variance "
    "⟦\\sigma^2(b) = \\sigma^2(s) - 2b\\,\\mathrm{Cov}(s,f) + b^2\\sigma^2(f)‖σ²(b) = σ²(s) − 2b·Cov(s, f) + b²·σ²(f)⟧, "
    "which is smallest at the regression slope ⟦\\beta = \\mathrm{Cov}(s,f)/\\sigma^2(f)‖β = Cov(s, f) / σ²(f)⟧. Any "
    "other ratio pays a penalty that grows with the square of its distance from ⟦\\beta‖β⟧:"
)
equation(r"\sigma^2(b) - \sigma^2(\beta) = \sigma^2(f)\,(b-\beta)^2 .", "σ²(b) − σ²(β) = σ²(f)·(b − β)²")
para(
    "The naïve hedge sets ⟦b = 1‖b = 1⟧ and so pays a fixed penalty ⟦\\sigma^2(f)(1-\\beta)^2‖σ²(f)(1 − β)²⟧, a bias "
    "that is negligible whenever ⟦\\beta‖β⟧ is close to one. A ratio estimated from the previous 52 weeks pays, on "
    "average, ⟦\\sigma^2(f)‖σ²(f)⟧ times the mean squared error of the estimate: a variance cost, which is large when "
    "the estimate rests on few observations (Appendix C.5). The naïve hedge is therefore the better choice whenever"
)
equation(r"(1-\beta)^2 < \mathrm{E}\big[(\hat b-\beta)^2\big],", "(1 − β)² < E[(b̂ − β)²]")
para(
    "that is, whenever the true ratio is closer to one than the estimated ratio is to the truth. Tail-risk objectives "
    "have no closed form, but the same trade-off should apply, and the noise side should be larger, because a ratio "
    "fitted to the worst weeks of a year is fitted to a handful of observations. The question is thus an empirical one, "
    "and Section 5.4 measures both sides of the inequality."
)
para(
    "The counterargument is basis risk. A one-for-one hedge is optimal only if spot and futures prices move together "
    "one for one. Where they do not, an estimated ratio can adapt and the naïve ratio cannot. In Cao and Conlon's own "
    "Table 13 the OLS hedge removes slightly more variance than the naïve hedge when basis risk is above its median in "
    "three of the four markets. Bitcoin and "
    "natural gas are therefore the hard test: if the naïve hedge fails anywhere, it should fail there. They test "
    "different things. In natural gas the best ratio turns out to be almost exactly one, so the question is how much "
    f"noise estimation adds. In Bitcoin the best ratio is furthest from one ({BN.loc['BTC', 'beta']:.2f}), so it is the "
    "stronger test of the naïve hedge's bias. Section 5.5 examines this directly."
)

# ------------------------------------------------------------------ 3 data

heading("3. Data")
n_orig = {m: A[m]["n"] + 52 for m in H1}
rows = [
    ["WTI crude oil", "Cushing spot (FRED DCOILWTICO)", "NYMEX CL", "Jan 1990 – Nov 2026", f"{F['WTI']['n'] + 52:,}"],
    ["GBP/USD", "Bloomberg GBPUSD", "CME BP", "Jan 1990 – Nov 2026", f"{F['GBPUSD']['n'] + 52:,}"],
    ["S&P 500", "Bloomberg SPX", "CME SP to Sep 2021, then ES", "Jan 1990 – Nov 2026", f"{F['SP500']['n'] + 52:,}"],
    ["Gold", "Bloomberg XAU", "COMEX GC", "Jan 1990 – Nov 2026", f"{F['GOLD']['n'] + 52:,}"],
    ["Bitcoin", "CME CF reference rate (BRR)", "CME BTC", "Dec 2017 – Nov 2026", f"{F['BTC']['n'] + 52:,}"],
    ["Natural gas", "Henry Hub: Bloomberg to Mar 2007, FRED DHHNGSP after", "NYMEX NG", "Jan 1999 – Nov 2026", f"{F['NATGAS']['n'] + 52:,}"],
]
para(
    "Table 1 lists the six markets. Futures prices and contract calendars are from Bloomberg (Bloomberg L.P., 2026); "
    "spot prices are from Bloomberg and from the FRED database (Federal Reserve Bank of St. Louis, 2026). All series are daily and were sampled weekly on "
    "Wednesdays, as in the paper. Returns are log price changes. The Chicago Fed National Activity Index (CFNAI) from "
    "FRED identifies periods of below-average growth. Four details differ from our revised proposal. The natural gas "
    "sample starts in January 1999, not 1997, because Bloomberg's Henry Hub spot series begins then and the FRED series "
    "is too sparse in its first years to use. The spot sources for WTI and gold are not the ones we proposed, for the "
    "reasons given in Section 3.1. We classify economic regimes with the CFNAI alone, as the paper does, without the "
    "NBER recession indicator. And for the extension and the two new markets we compute each futures return on a single "
    "contract, not with the paper's roll convention as proposed; Section 3.2 gives the reason and reports the effect."
)
table("Markets, sources and samples", ["Market", "Spot price", "Futures", "Sample", "Weekly returns"], rows,
      [1.05, 2.45, 1.45, 1.35, 0.7],
      note="Weekly returns are counts in the same-contract setting (Section 3.2). The first 52 weeks of each market are used only "
           "to estimate the first hedge ratio.")
heading("3.1 Reconstructing the paper's data conventions", 2)
para(
    "The paper describes its data in one paragraph: weekly Wednesday prices, 1,728 weekly observations, and futures that are "
    "“nearest to maturity, with a rollover to the subsequent contract occurring on the first day of the contract month” (p. 983). "
    "It does not say how holidays are handled or how returns are computed in a week when the contract changes. We "
    "inferred both from its summary statistics."
)
para(
    "*Calendar.* There are 1,748 Wednesdays between January 3, 1990 and June 28, 2023. On 20 of them at least one of the "
    "markets was closed. Keeping only Wednesdays on which every market traded leaves exactly 1,728 dates, the paper's "
    "count. The paper therefore appears to drop holiday Wednesdays without replacement. The paper's 1,728 are returns. "
    "Our data begin on January 2, 1990, so the first of the 1,728 dates has no return and we have 1,727."
)
para(
    "*Roll weeks.* Futures returns in the paper match a spliced series: in a roll week the new contract's price is "
    "compared with the old contract's price a week earlier. For WTI the stated roll rule cannot operate, because the "
    "contract stops trading about a week before its contract month begins, and the series reduces to the front contract "
    "held to expiry. Table 2 compares our reconstruction with the paper's Table 2. Futures statistics match closely in "
    "all four markets, and spot statistics match for WTI and the S&P 500."
)
t2 = R.table2.pivot_table(index=["market", "series"], columns="statistic", values=["ours", "paper"], sort=False)
rows = []
for m in H1:
    for s in ("spot", "futures"):
        r = t2.loc[(m, s)]
        rows.append([f"{L[m]}, {s}"] + [f"{r[('ours', k)]:.3f} / {r[('paper', k)]:.3f}"
                                         for k in ("std", "min", "max", "excess_kurtosis", "cvar_5pct")])
table("Weekly returns, January 1990 to June 2023: our reconstruction / Cao and Conlon (2025), Table 2",
      ["Series", "Std. dev.", "Minimum", "Maximum", "Excess kurtosis", "5% CVaR"], rows, [1.5, 1.05, 1.1, 1.05, 1.2, 1.1],
      note="Each cell shows our value, then the paper's. Futures are spliced under the paper's roll rule. CVaR is shown "
           "with the paper's sign, as a return; elsewhere in this report it is a positive loss.")
para(
    "Two differences remain, and both come from the spot source. The paper uses the WM/Reuters rate for GBP/USD and the "
    "London bullion price for gold. We do not have access to either and use Bloomberg's closing quotes, which are taken "
    "later in the day and closer to the time the futures settle. Our spot and futures returns are therefore more closely "
    "aligned than the paper's, and our hedging effectiveness for these two markets is higher (Section 5.1). For WTI, "
    "Bloomberg's spot series at NYU begins in 2017, so we use the Energy Information Administration's Cushing price from "
    "FRED. It has no price on some Wednesdays; on those weeks we read both spot and futures on the nearest earlier day so "
    "that the two legs always share a date."
)
heading("3.2 Two data settings", 2)
para(
    "Spliced returns reproduce the paper, but they include a price gap in roll weeks that no hedger experiences. A "
    "hedger who rolls from one contract to the next earns the return on each contract while holding it. We therefore keep "
    "two settings. The *paper setting* (strict Wednesdays apart from the WTI substitution above, spliced returns) is used to replicate the original sample. "
    "The *same-contract setting* computes every futures return on a single contract and, when a Wednesday is missing, "
    "moves the observation for both legs to Tuesday or Monday. It is used for the extension to 2026 and for Bitcoin and "
    "natural gas, and as a robustness check on the replication. The choice matters most for natural gas, where the next "
    f"contract is on average {gap_ng.mean() * 100:.1f}% more expensive than the expiring one at the roll and the gap has "
    f"been as large as {gap_ng.abs().max() * 100:.0f}%; a spliced series would record these gaps as hedging losses."
)
para(
    "For natural gas we combine two spot sources. FRED's Henry Hub series is sparse before 2007, and Bloomberg's series "
    "is dated one trading day late between January 2020 and March 12, 2021. We confirmed the second problem with three "
    "tests on the raw files: in that window Bloomberg has a price on none of the 56 Mondays on which the futures "
    "traded, it has prices on five exchange holidays, and its daily changes correlate with the previous day's futures "
    "change (0.34) and not with the same day's (0.02). We use Bloomberg before April 2007 and FRED "
    "from then on, and every weekly return uses one source at both ends."
)

# ------------------------------------------------------------------ 4 method

heading("4. Methodology")
para(
    "Let ⟦s_t‖s(t)⟧ and ⟦f_t‖f(t)⟧ be the weekly log returns of the spot and futures prices. A hedger who is long one "
    "unit of spot and short ⟦b‖b⟧ units of futures earns, in week ⟦t‖t⟧,"
)
equation(r"y_t(b) = s_t - b\,f_t ,", "y(t) = s(t) − b·f(t)")
para(
    "where the hedge ratio ⟦b‖b⟧ is fixed at the end of week ⟦t-1‖t − 1⟧. Downside risk, the concern of this short "
    "hedger, is the lower tail of ⟦y_t‖y(t)⟧. Upside risk, the concern of a hedger who is short spot and long futures "
    "and earns ⟦-y_t‖−y(t)⟧, is its upper tail (equations 1 and 2 of Cao and Conlon). Each week, each estimated model in Table 3 chooses "
    "the ratio that minimizes its own measure of risk, ⟦\\rho‖ρ⟧, over the previous 52 weeks only:"
)
equation(r"\hat b_t = \operatorname*{arg\,min}_{b\,\in\,\{0,\,0.01,\,\ldots,\,2\}} \rho\big(y_{t-52}(b),\ldots,y_{t-1}(b)\big).",
         "b̂(t) = the value of b in {0, 0.01, ..., 2} that minimizes ρ(y(t−52), ..., y(t−1))")
rows = [
    ["Naïve", "b = 1", "Nothing is estimated."],
    ["OLS", "Minimum variance", "Slope of spot on futures returns (Ederington, 1979)."],
    ["Historical simulation (HS)", "Minimum VaR or CVaR", "Empirical tail of the 52 hedged returns (Harris & Shen, 2006)."],
    ["Cornish–Fisher (CFE)", "Minimum VaR or CVaR", "Normal quantile adjusted for skewness and kurtosis (Cao et al., 2010)."],
    ["Copula", "Minimum VaR or CVaR", "Clayton (1978) copula with empirical marginals; 10,000 simulated weeks per window."],
    ["Semivariance", "Minimum semivariance", "Mean squared loss below zero."],
]
table("The six hedge-ratio models", ["Model", "Objective", "How the ratio is obtained"], rows, [1.75, 1.45, 3.3])
para(
    "The HS, CFE and copula models are estimated separately for VaR and CVaR at the 10%, 5% and 1% levels, for downside "
    "and upside risk, which gives 2 × 2 × 3 = 12 scenarios per market. The minimization in equation (4) is a grid search "
    "from 0 to 2 in steps of 0.01, except for OLS, whose ratio is the regression slope. Hedging effectiveness is the share of the unhedged risk that the hedge removes,"
)
equation(r"\mathrm{HE} = 1 - \frac{\rho(\text{hedged position})}{\rho(\text{unhedged position})},",
         "HE = 1 − ρ(hedged position) / ρ(unhedged position)")
para(
    "measured over all out-of-sample weeks with historical-simulation VaR and CVaR, and also with variance and "
    "semivariance (Cotter & Hanly, 2006). Ranking the models by HE within a scenario is a fair comparison, because every "
    "model is evaluated on the same weeks and the same unhedged risk."
)
para(
    "To test whether an estimated model beats the naïve hedge we follow the paper and use the test of Wilcox et al. "
    "(2014): the relevant quantile of each hedged-return series is estimated with the Harrell and Davis (1982) estimator, "
    "and a percentile bootstrap gives a one-sided p-value for the hypothesis that the model has lower tail risk. The test "
    "compares quantiles in every scenario: in a CVaR scenario it compares the quantiles of the returns produced by the "
    "CVaR-minimizing ratios. The hypotheses also name semivariance: we report its effectiveness (Table 24 in Appendix A) "
    "but, like the paper, test only quantiles. The test resamples the two series independently. That is conservative here, because the two "
    "series come from the same weeks and are highly correlated (the median correlation between a model's hedged returns "
    f"and the naïve hedge's is {np.median(CORR):.2f}). We therefore add a *paired* version that resamples whole weeks. It "
    "has more power to detect a difference in either direction. Both versions resample weeks as if they were "
    "independent, so neither allows for the clustering of volatile weeks (Section 6)."
)
para(
    "*Reading the results.* Two numbers carry the evidence. An HE of 0.80 for 5% CVaR means that the average loss in the "
    "worst 5% of weeks is one fifth as large with the hedge as without it. The p-value is the share of bootstrap samples "
    "in which the model's tail risk comes out larger than the naïve hedge's. A value near 0 therefore favors the model, a "
    "value near 0.5 means the data cannot tell the two apart, and a value near 1 favors the naïve hedge. In this report "
    "p < 0.10 means that a model is significantly better at the 10% level, and, for the paired test, p > 0.95 means that "
    "the naïve hedge is significantly better at the 5% level. Appendix C states the models, the measures and the test "
    "formally."
)
para(
    "Three further analyses address the reason for the result: an in-sample run in which each week's ratio is estimated "
    "on the 52 weeks ending in that week; splits of the evaluation weeks by basis volatility and by the sign of the "
    "CFNAI; and the opportunity cost of the naïve hedge in mean–variance utility, with risk aversion of 6 and a "
    "transaction cost of 0.03% of turnover, as in the paper. All code is in Python, is covered by automated tests, and "
    "is in the project repository (Appendix B)."
)
para(
    "*What follows the paper and what we add.* The six models, the 52-week window, the 12 scenarios, the effectiveness "
    "measures, the test of Wilcox et al. (2014), the in-sample comparison, the utility calculation and the splits by "
    "basis risk and by the CFNAI are the paper's, and every main result is reported in that form first. We add four "
    "things as supplements, not as replacements: the same-contract returns of Section 3.2, the paired version of the "
    "paper's test, the comparison of bias with noise in Section 5.4, and the stress episodes and robustness checks of "
    "Sections 5.6 and 5.8."
)

# ------------------------------------------------------------------ 5 results

heading("5. Results")
heading("5.1 Replication, 1990 to June 2023 (H1)", 2)
para(
    "Table 4 compares the tail-risk effectiveness of the naïve hedge in our data with the paper's Table 5. For WTI and "
    f"the S&P 500 the two agree closely: the mean absolute difference across the 12 scenarios is {diff['WTI'].mean():.3f} "
    f"and {diff['SP500'].mean():.3f}. For GBP/USD and gold our hedge is more effective than the paper's, by "
    f"{(naive['GBPUSD'].to_numpy() - np.array(PAPER_NAIVE['GBPUSD'])).mean():.2f} and "
    f"{(naive['GOLD'].to_numpy() - np.array(PAPER_NAIVE['GOLD'])).mean():.2f} on average. This is the spot-source "
    "difference described in Section 3.1, and it appears in variance terms as well: our OLS hedge removes "
    f"{R.grid('paper', 'GBPUSD', 'original', val='he_var').loc['ols'].iloc[0] * 100:.0f}% of GBP/USD variance against "
    f"{PAPER_OLS_VAR_HE['GBPUSD'] * 100:.0f}% in the paper. The levels differ, but the question is the ranking of the "
    "models, which uses the same data for every model."
)
rows, bold = [], set()
for m in H1:
    rows.append([f"{L[m]}: ours"] + [fmt(v) for v in naive[m]])
    rows.append([f"{L[m]}: paper"] + [fmt(v) for v in PAPER_NAIVE[m]])
table("Tail-risk hedging effectiveness of the naïve hedge, 1990 to June 2023: this study and Cao and Conlon (2025)",
      [""] + COL_LABELS, rows, [1.0] + [0.46] * 12, size=7.5,
      note="Columns 1–6 are downside risk and columns 7–12 upside risk. Paper setting, out-of-sample, 52-week window.")
para(
    "In money terms, the levels are large. On an unhedged $100 million WTI position the average loss in the worst 5% of "
    f"weeks between 1991 and June 2023 was about ${loss_unhedged:.1f} million; with the naïve hedge it was about "
    f"${loss_naive:.1f} million (both in simple returns). The comparisons that follow are about the much smaller differences between hedge ratios "
    "once most of this risk has been removed."
)


def score_rows(d, markets, ref=None):
    out = []
    for m in markets:
        r = d[m]
        out.append([L[m], f"{r['n']:,}"] + [str(r[k]) for k in MODELS] + [str(r["ind10"]), str(r["ind_half_n"]),
                                                                         str(r["pair05"]), str(r["pair95"])])
    return out


rows, groups = [], []
for title, d, markets in (
        ("A. Replication: January 1990 to June 2023, paper setting", A, H1),
        ("B. Extension: July 2023 to November 2026, same-contract setting", C, H1),
        ("C. Full sample to November 2026, same-contract setting", F, H1),
        ("D. New markets, full sample, same-contract setting", D, H2)):
    groups.append(len(rows))
    rows.append([title] + [""] * 11)
    rows += score_rows(d, markets)
table("Scorecard: scenarios won by each model and tests against the naïve hedge",
      ["Market", "Weeks", "Naïve", "OLS", "HS", "CFE", "Copula", "SV", "p < 0.10", "p > 0.5", "Paired p < 0.05", "Paired p > 0.95"],
      rows, [0.85, 0.52, 0.5, 0.42, 0.38, 0.42, 0.6, 0.38, 0.55, 0.5, 0.68, 0.7], size=8, group_rows=groups,
      note="Columns Naïve to SV count the scenarios (of 12) in which the model has the highest tail-risk effectiveness. "
           "The last four columns count the 60 tests of an estimated model against the naïve hedge (5 models × 12 "
           "scenarios): the Wilcox et al. (2014) test with p below 0.10 (model better) and with p above 0.5, and "
           "the paired test with p below 0.05 (model significantly better) and above 0.95 (naïve hedge significantly "
           "better). OLS and semivariance ratios do not depend on the risk measure, so their 12 CVaR tests repeat "
           "their 12 VaR tests and 48 of the 60 tests in each row are distinct. Each test uses 2,000 bootstrap samples. "
           "When we repeated all tests with different random draws, no entry in the p < 0.10 or paired p < 0.05 columns "
           "changed, and entries in the other two columns changed by at most four. WTI has fewer weeks than the other "
           "markets because in some weeks its spot series has no price on Wednesday, Tuesday or Monday.")
others = sum(A[m][k] for m in H1 for k in ("hs", "cfe", "copula"))
para(
    f"Panel A of Table 5 gives the main replication result. The naïve hedge is the most effective model in "
    f"{A['WTI']['naive']} of 12 scenarios for WTI, {A['GBPUSD']['naive']} for GBP/USD, {A['SP500']['naive']} for the S&P "
    f"500 and {A['GOLD']['naive']} for gold. The paper reports {PAPER_NAIVE_WINS['WTI']}, {PAPER_NAIVE_WINS['GBPUSD']}, "
    f"{PAPER_NAIVE_WINS['SP500']} and {PAPER_NAIVE_WINS['GOLD']}. As in the paper, OLS, the simplest estimated model, "
    f"takes nearly all the remaining scenarios; the three tail-specific models (HS, CFE and copula) together win "
    f"{others} of 48. When an estimated model is ahead, the margin is small: the largest gain over the naïve hedge in "
    f"any scenario is {max((R.grid('paper', m, 'original').drop('naive').max() - naive[m]).max() for m in H1):.2f}."
)
para(
    f"Our counts differ from the paper's for WTI and the S&P 500 although our returns for those markets match the "
    f"paper's closely. The reason is that most scenarios are near-ties. In {sum(near_ties('paper', m, 'original') for m in H1)} "
    f"of the 48 scenarios, and in all {near_ties('paper', 'SP500', 'original')} for the S&P 500, the naïve hedge and the "
    "best estimated model are within 0.005 of each other in effectiveness, so a difference in the third decimal place "
    "of one series changes which model is counted as the winner. The count of wins is therefore a fragile statistic, "
    "in the paper as in our data, and we rest the conclusion on the tests."
)
para(
    f"None of the {60 * 4} tests rejects in favor of an estimated model at the 10% level (the smallest p-value is "
    f"{P_MIN:.2f}). This test is conservative for correlated series (Section 4), so the absence of rejections is weak "
    "evidence by itself. Between "
    f"{min(A[m]['ind_half'] for m in H1) * 100:.0f}% and {max(A[m]['ind_half'] for m in H1) * 100:.0f}% of the p-values "
    "in each market are above 0.5, in line with the paper's statement that the majority are. The paired test goes "
    f"further. It also finds no case in which an estimated model is better at the 5% level, and in {N_DIST_PAIR95} of "
    f"the {N_DIST} distinct comparisons it finds the naïve hedge significantly better at the 5% level, or in "
    f"{N_NOCOP_PAIR95} of {N_NOCOP} when the copula model, which is misspecified (Section 6), is left out (Table 23 in "
    f"Appendix A). Table 5 counts {tot(A, 'pair95')} of {60 * 4} because it includes the repeated OLS and semivariance "
    "tests. On this evidence the three tail-specific "
    f"models are not just no better than the naïve hedge but worse in most comparisons ({N_TAIL3_PAIR95} of their {N_TAIL3} tests). "
    "For the OLS and semivariance hedges the paired test agrees with the paper in most cases: it finds a significant "
    f"difference in {N_OLSSV_PAIR95} of {N_OLSSV}. H1 also names "
    "semivariance, which the tests do not cover. Measured directly, the naïve hedge removes the largest share of downside "
    f"semivariance in {sum(semi_best[m] == 'naive' for m in H1)} of the four markets and is within "
    f"{max(float(SEMI[m][['ols', 'sv']].max() - SEMI[m]['naive']) for m in H1):.4f} of the best hedge in the others "
    "(Table 24 in Appendix A). The ordering is the paper's: in its Table 6 the naïve hedge is also first for WTI and "
    "GBP/USD and the OLS hedge first for the S&P 500 and gold. H1 holds in the original sample. Appendix A gives the full tables."
)

heading("5.2 Persistence, July 2023 to November 2026 (H1)", 2)
para(
    f"Panel B evaluates the {C['WTI']['n']} weeks after the paper's sample ends, using same-contract returns. The naïve hedge "
    f"is the best model in {C['WTI']['naive']} of 12 scenarios for WTI, {C['GBPUSD']['naive']} for GBP/USD and "
    f"{C['GOLD']['naive']} for gold, and no estimated model beats it at the 10% level in any market under the paper's "
    "test. The S&P 500 is the exception, and we report it as one. There the naïve hedge wins "
    f"{C['SP500']['naive']} scenarios, and the paired test finds an estimated model significantly better at the 5% level "
    f"in {C['SP500']['pair05']} of 60 comparisons ({sp_flags_distinct} distinct tests: the OLS and CFE hedges in the 10% "
    "downside scenarios). The differences are measurable but very small: every model except the copula removes "
    f"{sp_post_ours.drop('copula').loc[:, 'down'].min().min() * 100:.0f}% or more of the S&P 500 downside tail in this "
    "period, so the ranking is decided in the third decimal place of effectiveness. Effectiveness is this high because "
    f"the hedged position barely moves: its weekly standard deviation is {sp_hedged_sd_post * 100:.2f}% after June 2023, "
    f"against {sp_hedged_sd_pre * 100:.2f}% before. No comparison is flagged in the "
    "other three markets."
)
para(
    f"With {C['WTI']['n']} weeks the 1% tail holds two observations, so we place more weight on Panel C, which adds the new "
    "weeks to the original sample. Over the whole period the naïve hedge wins "
    f"{F['WTI']['naive']}, {F['GBPUSD']['naive']} and {F['GOLD']['naive']} of 12 scenarios for WTI, GBP/USD and gold. For "
    f"the S&P 500 it wins {F['SP500']['naive']} and the OLS hedge wins {F['SP500']['ols']}, by at most "
    f"{sp_full_margin:.3f} in effectiveness. Neither test finds any model significantly better than the naïve hedge in "
    "any of the four markets (Tables 18 to 21 in Appendix A give the full results). H1 therefore holds through November "
    "2026 in the sense in which we stated it: no model significantly and consistently outperforms the naïve hedge. The "
    "S&P 500 shows that this is a weaker statement than the naïve hedge winning every count."
)

heading("5.3 Bitcoin and natural gas (H2)", 2)
sel = [("down", "VaR", 0.05), ("down", "CVaR", 0.05), ("down", "CVaR", 0.01), ("up", "VaR", 0.05), ("up", "CVaR", 0.05), ("up", "CVaR", 0.01)]
rows, groups, bold = [], [], set()
for m, g in (("BTC", btc), ("NATGAS", ng)):
    groups.append(len(rows))
    rows.append([f"{L[m]} ({D[m]['n']:,} weeks)"] + [""] * 6)
    best = g[sel].idxmax()
    for model in MODELS:
        for j, c in enumerate(sel):
            if best[c] == model:
                bold.add((len(rows), j + 1))
        rows.append([label(model)] + [fmt(g.loc[model, c]) for c in sel])
ols_below = int((ng.loc["ols"] < ng.loc["naive"]).sum())
para(
    f"Table 6 and Panel D of Table 5 report the new markets. For Bitcoin the naïve hedge removes "
    f"{btc.loc['naive'].min() * 100:.0f}% to {btc.loc['naive'].max() * 100:.0f}% of tail risk and is the best model in "
    f"{D['BTC']['naive']} of 12 scenarios. The semivariance and HS hedges win most of the others, mainly for upside risk. "
    f"The sample is short: {D['BTC']['n']} weeks hold about four observations in the 1% tail. No estimated model beats "
    f"the naïve hedge at the 10% level (the smallest p-value is {D['BTC']['min_p']:.2f}), and the paired test finds none "
    f"better at the 5% level and the naïve hedge significantly better in {D['BTC']['pair95']} of 60 comparisons."
)
table("Bitcoin and natural gas: tail-risk hedging effectiveness by model, full sample",
      ["", "VaR 5%", "CVaR 5%", "CVaR 1%", "VaR 95%", "CVaR 95%", "CVaR 99%"], rows, [1.9] + [0.75] * 6, bold=bold,
      group_rows=groups, note="Same-contract setting, out-of-sample. The best model in each column is in bold. The first "
                              "three columns are downside risk; the last three are upside risk.")
para(
    f"Natural gas is the more demanding case. The futures hedge is far less effective than in any other market: the "
    f"naïve hedge removes only {ng.loc['naive'].min() * 100:.0f}% to {ng.loc['naive'].max() * 100:.0f}% of tail risk and "
    f"{ng_var.loc['naive'].iloc[0] * 100:.0f}% of variance. Henry Hub spot is a price for gas delivered the next day, "
    "and weather can move it far from the futures price, which covers delivery over the following month. In the week of "
    f"Winter Storm Uri the spot price rose from ${uri.loc['2021-02-10', 'spot_price']:.2f} to "
    f"${uri.loc['2021-02-17', 'spot_price']:.2f} per million Btu and fell back to "
    f"${uri.loc['2021-02-24', 'spot_price']:.2f} a week later, while the futures contract we hold rose by about "
    f"{(np.exp(uri.loc['2021-02-17', 'fut_logret']) - 1) * 100:.0f}% and fell by about "
    f"{(1 - np.exp(uri.loc['2021-02-24', 'fut_logret'])) * 100:.0f}% in the following week. No hedge ratio protects against that. This is exactly the "
    "setting in which the counterargument of Section 2.3 expects estimated ratios to help. They do not: the naïve hedge "
    f"is the best model in {D['NATGAS']['naive']} of 12 scenarios, the OLS hedge is less effective than the naïve hedge "
    f"in {ols_below} of 12, no test favors an estimated model, and the paired test finds the naïve hedge "
    f"significantly better in {D['NATGAS']['pair95']} of 60 comparisons. H2 holds for both markets."
)

heading("5.4 Is the reason estimation error?", 2)
para(
    "The three signs of estimation error set out in Section 2.3 are all present. First, estimated ratios are unstable. "
    "Figure 1 plots the weekly ratios that minimize 5% CVaR for WTI. The OLS and semivariance ratios stay close to one. "
    "The HS and CFE ratios, which are fitted to the tail of 52 observations, jump between about 0.5 and 1.5 as single "
    "extreme weeks enter and leave the window. Table 7, the counterpart of the paper's Table 3, shows the same pattern in "
    "every market, and it is most pronounced "
    f"in natural gas, where even the OLS ratio has a standard deviation of {sd('ours', 'NATGAS', 'ols'):.2f}. The copula "
    f"ratio is stable but biased: for downside risk it averages about {cop4:.2f} in the four original markets, against "
    f"about 0.8 in the paper, and {cop2:.2f} in Bitcoin and natural gas, and so under-hedges systematically."
)
figure("fig1_hedge_ratios_wti.png", "Hedge ratios that minimize 5% CVaR (downside), WTI, 52-week rolling window, "
                                     "1991 to June 2023. The dashed line is the naïve ratio of one.", 5.0)
rows = []
for st, m, sm in MAIN:
    rows.append([L[m]] + [f"{mean_b(st, m, k):.2f} ({sd(st, m, k):.2f})" for k in MODELS if k != "naive"])
table("Hedge ratios that minimize 5% CVaR (downside): mean and standard deviation over time",
      ["Market", "OLS", "HS", "CFE", "Copula", "Semivariance"], rows, [1.3] + [1.02] * 5,
      note="Standard deviations in parentheses. Original sample for the first four markets (paper setting); full sample "
           "for Bitcoin and natural gas (same-contract setting). The naïve ratio is 1 with no variation. Ratios are limited "
           f"to the range 0 to 2; the CFE ratio is at a limit in {at_limit('ours', 'NATGAS') * 100:.0f}% of natural gas weeks "
           "and almost never elsewhere (Appendix B).")
rows = [[L[m], f"{BN.loc[m, 'beta']:.3f}", f"{BN.loc[m, 'r2']:.2f}", f"{BN.loc[m, 'bias']:.3f}", f"{BN.loc[m, 'noise_ols']:.3f}",
         f"{BN.loc[m, 'noise_hs']:.3f}", f"{BN.loc[m, 'noise_cfe']:.3f}"] for _, m, _ in MAIN]
para(
    "Table 8 is our addition to the paper's evidence. It puts numbers on the two sides of inequality (2). In every market the variance-minimizing ratio is close to "
    f"one, between {BN.beta.min():.2f} and {BN.beta.max():.2f}, so the bias of the naïve hedge is small. For OLS the "
    "noise is of the same order as that bias: it is "
    f"{min(v for m, v in ols_mult.items() if m != 'BTC'):.1f} to {max(ols_mult.values()):.1f} times the bias in WTI, "
    "GBP/USD, the S&P 500 and gold, and slightly below it in Bitcoin. This is what the near-ties between the naïve and "
    "OLS hedges in Table 5 look like from the side of the hedge ratio: neither has a clear edge. For the tail-risk "
    f"models the noise is far larger. The variance of the HS ratio is {min(hs_mult.values()):.0f} to "
    f"{max(hs_mult.values()):.0f} times the naïve hedge's bias in the five markets other than natural gas, and the "
    f"Cornish–Fisher ratio is noisier than the HS ratio in {cfe_noisier} of the six markets. Natural gas is the extreme "
    f"case. Its variance-minimizing ratio is {BN.loc['NATGAS', 'beta']:.3f}, so the naïve hedge has almost no bias, while "
    f"its low ⟦R^2‖R²⟧ of {BN.loc['NATGAS', 'r2']:.2f} makes every estimate noisy: there even the OLS ratio is noisier than the HS ratio. That is "
    f"consistent with the OLS hedge being less effective than the naïve hedge in all {ols_below} natural gas scenarios "
    "(Section 5.3)."
)
para(
    "Two cautions apply to Table 8. First, the noise columns contain two things: sampling error, and movement of the "
    "best ratio itself, which an estimate from the past year also fails to track. For OLS the two can be separated. "
    f"Sampling error alone (equation 21 in Appendix C.5) gives {se2('WTI'):.2f} for WTI and {se2('NATGAS'):.1f} for natural "
    f"gas, against {BN.loc['WTI', 'noise_ols']:.2f} and {BN.loc['NATGAS', 'noise_ols']:.1f} in the table. Most of the "
    "natural gas figure is therefore movement in the ratio, not sampling error, although either number is far above "
    "the naïve hedge's bias there. Second, the comparison is exact only for variance; for tail risk it is an "
    "indication, not a test. In variance terms the two hedges can be compared directly: out of sample the naïve hedge "
    f"removes at least as much variance as the OLS hedge in {len(var_naive_ahead)} of the six markets, and in the sixth, "
    "the S&P 500, the two differ only in the fifth decimal place (Table 24 in Appendix A). The match with Table 8 is "
    "broad, not exact market by market: in Bitcoin, where OLS noise is slightly below the bias, the naïve hedge is "
    "still ahead, and in the S&P 500, where noise is twice the bias, the two tie. One reason is that the bias column "
    "uses a single whole-sample ratio, while the best ratio moves over time."
)
table("The cost of fixing the ratio at one against the noise of estimating it",
      ["Market", "⟦\\beta‖β⟧", "⟦R^2‖R²⟧", "Bias of naïve", "Noise: OLS", "Noise: HS", "Noise: CFE"], rows,
      [1.3, 0.8, 0.8, 1.1, 1.0, 1.0, 1.0],
      note="⟦\\beta‖β⟧ is the variance-minimizing hedge ratio and ⟦R^2‖R²⟧ the share of spot variance explained by "
           "futures, both over the whole sample, including the first 52 weeks that the out-of-sample tables leave out. The bias of the naïve hedge is ⟦(1-\\beta)^2‖(1 − β)²⟧. Noise is the "
           "variance over time of each model's ratio; for HS and CFE it is the 5% CVaR (downside) ratio of Table 7. The "
           "last four columns are multiplied by 100 and correspond to the two sides of inequality (2). Variance over "
           "time includes genuine changes in the best ratio as well as sampling noise, so the noise columns are upper "
           "bounds on sampling noise. Samples as in Table 7.")
para(
    "Second, the estimated models win in-sample, as they do in the paper's Table 9 (Table 22 in Appendix A gives our "
    "counts by model). Figure 2 counts the scenarios in which the naïve hedge is the best "
    "model when each ratio is evaluated on the weeks it was estimated on, and when it is applied to the following week. "
    f"In-sample the naïve hedge is best in {A_IS['WTI']}, {A_IS['GBPUSD']}, {A_IS['SP500']} and {A_IS['GOLD']} of 12 "
    f"scenarios in the four original markets and in {D_IS['BTC']} and {D_IS['NATGAS']} for Bitcoin and natural gas; the "
    "paper reports 1, 3, 3 and 3. Most of the models are therefore not badly specified: they do find ratios that would "
    "have reduced tail risk further (Section 6 takes them one by one). Third, that advantage does not survive the step to the next week: out-of-sample, the "
    "best estimated model loses on average "
    f"{np.mean([is_gain(*k) for k in MAIN[:4]]):.3f} of effectiveness in the original markets relative to its in-sample "
    f"result, which is the whole of its in-sample lead over the naïve hedge ({np.mean([is_lead(*k) for k in MAIN[:4]]):.3f}). "
    f"In natural gas it loses {is_gain('ours', 'NATGAS', 'full'):.3f}, more than its in-sample lead of "
    f"{is_lead('ours', 'NATGAS', 'full'):.3f}."
)
para(
    "Unstable ratios, in-sample wins that do not carry over, and noise that exceeds the naïve hedge's bias are what "
    "estimation error predicts. Each prediction could have failed, in any of the six markets. One did, narrowly: in "
    "Bitcoin the OLS ratio's noise is slightly below the naïve hedge's bias (Table 8). The others held everywhere. That "
    "is the sense in which the evidence supports estimation error as the explanation (Section 6 gives its limits)."
)
figure("fig2_naive_wins_in_vs_out.png", "Scenarios (of 12) in which the naïve hedge has the highest tail-risk "
                                         "effectiveness, out-of-sample and in-sample.", 5.2)

heading("5.5 Basis risk and the economic cycle", 2)
rows, groups = [], []
for title, a, b in (("By basis volatility: below median / above median", "basis_low", "basis_high"),
                    ("By economic growth (CFNAI): below average / above average", "cfnai_below", "cfnai_above")):
    groups.append(len(rows))
    rows.append([title] + [""] * 4)
    for st, m, sm in MAIN:
        w = {s: R.wins(st, m, sm, subset=s) for s in (a, b)}
        v = {s: R.grid(st, m, sm, subset=s, val="he_var") for s in (a, b)}
        c = {s: R.grid(st, m, sm, subset=s) for s in (a, b)}
        k = ("down", "CVaR", 0.05)
        rows.append([L[m], f"{w[a]['naive']} / {w[b]['naive']}", f"{w[a]['ols']} / {w[b]['ols']}",
                     f"{c[a].loc['naive', k]:.3f} / {c[b].loc['naive', k]:.3f}",
                     f"{c[a].loc['ols', k]:.3f} / {c[b].loc['ols', k]:.3f}"])
bl = {m: (int(R.wins(st, m, sm, subset="basis_low")["naive"]), int(R.wins(st, m, sm, subset="basis_high")["naive"])) for st, m, sm in MAIN}
cf = {m: (int(R.wins(st, m, sm, subset="cfnai_below")["naive"]), int(R.wins(st, m, sm, subset="cfnai_above")["naive"])) for st, m, sm in MAIN}
gold_high = R.grid("paper", "GOLD", "original", subset="basis_high")
gold_margin = float((gold_high.drop("naive").max() - gold_high.loc["naive"]).max())
k5 = ("down", "CVaR", 0.05)
ngh = R.grid("ours", "NATGAS", "full", subset="basis_high")
goh, sph = R.grid("paper", "GOLD", "original", subset="basis_high"), R.grid("paper", "SP500", "original", subset="basis_high")
assert all(R.grid(st, m, sm, subset="basis_high").loc["ols", k5] < R.grid(st, m, sm, subset="basis_high").loc["naive", k5]
           for st, m, sm in MAIN if m not in ("GOLD", "SP500")) and goh.loc["ols", k5] > goh.loc["naive", k5] and sph.loc["ols", k5] > sph.loc["naive", k5]
para(
    "Table 9 repeats the paper's two conditional analyses, by basis risk (its Table 13) and by economic growth (its "
    "Tables 7 and 8), and uses the first to test the counterargument. If basis risk favored estimated ratios, the naïve hedge should win less often "
    "when the basis is volatile. Gold behaves this way: the naïve hedge wins "
    f"{bl['GOLD'][0]} of 12 scenarios in calm-basis weeks and {bl['GOLD'][1]} in volatile-basis weeks, where OLS and "
    f"the semivariance hedge are ahead, by at most {gold_margin:.3f} in effectiveness. This is the pattern in the "
    "paper's Table 13. It does not "
    f"generalize. For the S&P 500, Bitcoin and natural gas the naïve hedge wins more often when the basis is volatile "
    f"({bl['SP500'][1]}, {bl['BTC'][1]} and {bl['NATGAS'][1]} of 12) than when it is calm ({bl['SP500'][0]}, "
    f"{bl['BTC'][0]} and {bl['NATGAS'][0]}), and in volatile-basis weeks for natural gas the OLS hedge removes "
    f"{ngh.loc['ols', k5] * 100:.0f}% of the 5% CVaR against {ngh.loc['naive', k5] * 100:.0f}% for the naïve hedge. These are counts of wins, which Section 5.1 showed to be fragile, so the effectiveness "
    "columns of Table 9 carry more weight than the counts. On that measure the OLS hedge is ahead in volatile-basis "
    f"weeks for gold and the S&P 500, by {goh.loc['ols', k5] - goh.loc['naive', k5]:.3f} and "
    f"{sph.loc['ols', k5] - sph.loc['naive', k5]:.3f}, and behind for WTI, GBP/USD, Bitcoin and natural gas. Our "
    "reading is that a volatile basis has two effects. It makes the best ratio differ from one, which helps estimated "
    "models, and it makes that ratio harder to estimate from 52 weeks, which hurts them. For the variance-minimizing "
    "ratio the second effect has an exact form: the sampling variance of the OLS slope is proportional to "
    "⟦(1-R^2)/R^2‖(1 − R²)/R²⟧, which rises steeply as the link between spot and futures loosens (Appendix C.5). In "
    "natural gas the second effect clearly dominates; in Bitcoin, where the naïve hedge wins fewer scenarios overall, "
    "the evidence is weaker. We do not test this reading directly for the tail-risk models; doing so would need hedge "
    "ratios estimated on windows of different lengths."
)
table("Naïve and OLS hedges by basis volatility and by economic growth",
      ["Market", "Naïve wins (of 12)", "OLS wins (of 12)", "5% CVaR HE, naïve", "5% CVaR HE, OLS"], rows,
      [1.3, 1.3, 1.3, 1.3, 1.3], group_rows=groups,
      note="Out-of-sample. Basis volatility is the standard deviation of the weekly difference between spot and futures "
           "returns over the previous 52 weeks, split at its median. Original sample for the first four markets; full "
           "sample for Bitcoin and natural gas.")
para(
    "The split by economic growth gives a weaker pattern than the paper reports. The naïve hedge wins more scenarios in "
    f"weeks of below-average growth for the S&P 500 ({cf['SP500'][0]} against {cf['SP500'][1]}), gold ({cf['GOLD'][0]} "
    f"against {cf['GOLD'][1]}) and Bitcoin ({cf['BTC'][0]} against {cf['BTC'][1]}). For WTI, GBP/USD and natural gas "
    "the counts in the two regimes are within one of each other. In no market does the naïve hedge do clearly worse "
    "when growth is weak, which is when tail protection is most needed."
)

heading("5.6 Stress episodes", 2)
S = R.stress.set_index(["event", "market"])
pick = [("COVID crash, Feb-Apr 2020", "WTI"), ("COVID crash, Feb-Apr 2020", "SP500"), ("COVID crash, Feb-Apr 2020", "BTC"),
        ("Winter Storm Uri, Feb 2021", "NATGAS"), ("FTX collapse, Nov 2022", "BTC"), ("Yen carry unwind, Aug 2024", "SP500"),
        ("Yen carry unwind, Aug 2024", "BTC"), ("Tariff sell-off, Apr 2025", "WTI"), ("Tariff sell-off, Apr 2025", "SP500"),
        ("Tariff sell-off, Apr 2025", "NATGAS")]
est = [k for k in MODELS if k != "naive"]


def pct(logret):
    """Log return as a simple percentage with a true minus sign."""
    v = round((np.exp(logret) - 1) * 100, 1)
    return f"{'−' if v < 0 else ''}{abs(v):.1f}%"


rows = []
for e, m in pick:
    r = S.loc[(e, m)]
    best = max(est, key=lambda k: r[f"{k}_worst_week"])
    rows.append([e.replace("Feb-Apr", "Feb–Apr"), L[m], str(int(r["weeks"])), pct(r["unhedged_worst_week"]), pct(r["naive_worst_week"]),
                 f"{pct(r[f'{best}_worst_week'])} ({label(best)})", pct(min(r[f"{k}_worst_week"] for k in est))])
n_ahead = sum(np.exp(max(S.loc[k][f"{e}_worst_week"] for e in est)) - np.exp(S.loc[k]["naive_worst_week"]) > 0.02 for k in S.index)
removed = lambda k: 1 - min(np.exp(S.loc[k]["naive_worst_week"]) - 1, 0) / (np.exp(S.loc[k]["unhedged_worst_week"]) - 1)  # noqa: E731
weak_rest = {k for k in S.index if k not in pick and removed(k) < 0.5}
assert weak_rest == {("COVID crash, Feb-Apr 2020", "NATGAS"), ("Yen carry unwind, Aug 2024", "GOLD"),
                     ("Yen carry unwind, Aug 2024", "NATGAS"), ("Tariff sell-off, Apr 2025", "GOLD")}, weak_rest
assert all(max(S.loc[k][f"{e}_worst_week"] for e in est) - S.loc[k]["naive_worst_week"] < 0.01 for k in weak_rest)
table("Worst weekly return of a long spot position in stress episodes: unhedged and hedged",
      ["Episode", "Market", "Weeks", "Unhedged", "Naïve hedge", "Best estimated model", "Worst estimated model"], rows,
      [1.65, 0.8, 0.45, 0.7, 0.75, 1.35, 0.8], size=8.5,
      note="Out-of-sample hedge ratios that minimize 5% CVaR. Simple weekly returns; a negative value is a loss. The "
           f"best estimated model is known only after the fact. The table shows {len(pick)} of the {len(S)} "
           "episode–market pairs we computed; all of them are in results/tables/stress_events.csv in the repository.")
para(
    "The paper does not examine individual episodes. Table 10 adds the ones named in our proposal, to look at the weeks "
    "that matter most. In the market-wide episodes the naïve hedge removes nearly all of the "
    "loss in the S&P 500 and most of it in WTI and Bitcoin. The best estimated model, which can be identified only "
    f"afterwards, is more than two percentage points ahead in {n_ahead} of the {len(S)} episode–market pairs we computed, "
    "natural gas in April 2025. The column for the "
    "worst estimated model shows the other side of estimation. After the first weeks of the COVID crash the "
    "Cornish–Fisher ratio for WTI and the S&P 500 jumped to 2, the upper limit of our search grid, and the over-hedged "
    "position then lost heavily when prices rebounded. Two episodes show the limits of any futures hedge. In Winter Storm Uri "
    "the loss came from a spot price that the futures did not follow, and in the FTX collapse the naïve hedge removed "
    "less than half of the worst weekly loss in Bitcoin's reference rate. The same is true of "
    "four pairs not shown in the table: gold in August 2024 and April 2025, and natural gas in March 2020 "
    "and August 2024. These are failures of the instrument, not of "
    "the hedge ratio: no estimated model did materially better."
)

heading("5.7 Cost of the naïve hedge", 2)
ubc = {m: utility_before_costs(st, m, sm) for st, m, sm in MAIN}
rows = []
for st, m, sm in MAIN:
    u = R.grid(st, m, sm, val="utility")
    d_ = (u.loc["naive"] - u).drop("naive")
    rows.append([L[m]] + [f"{d_.loc[k].mean():.4f}" for k in est] + [f"{d_.min().min():.4f}"])
table("Opportunity cost of the naïve hedge: utility of the naïve hedge minus utility of each estimated model",
      ["Market", "OLS", "HS", "CFE", "Copula", "Semivariance", "Smallest of 60"], rows, [1.2, 0.8, 0.8, 0.8, 0.8, 1.05, 1.05],
      note="Mean–variance utility of weekly hedged returns with risk aversion 6, less transaction costs of 0.03% of "
           "total turnover in the hedge ratio, as in the paper's equation 16. Average over the 12 scenarios. A positive "
           "value means the naïve hedge gives higher utility.")
para(
    "A fixed ratio could still be costly if it gave up return or added variance in ordinary weeks. Table 11 follows the "
    "paper's calculation (its Table 11) and reaches the paper's result: the utility of the naïve hedge is higher than that of every "
    "estimated model in all six markets and in every one of the 360 scenario comparisons, and for WTI our OLS figure of "
    f"{float((R.grid('paper', 'WTI', 'original', val='utility').loc['naive'] - R.grid('paper', 'WTI', 'original', val='utility').loc['ols']).mean()):.3f} "
    "equals the paper's 0.002. The result should be read with care, because it comes almost entirely from trading "
    "costs. The formula sets the cost of all turnover over the sample against a weekly mean and variance, which gives "
    "costs a large weight. Before costs, the difference between the naïve and OLS hedges is "
    f"between −{abs(min(ubc[m]['ols'] for m in H1 + ['BTC'])):.4f} and {max(ubc[m]['ols'] for m in H1 + ['BTC']):.4f} "
    "in five of the six markets, too small to matter in either direction. Natural gas is the exception: there the naïve hedge is ahead "
    f"of every estimated model before costs as well, by {min(ubc['NATGAS'].values()):.3f} to "
    f"{max(ubc['NATGAS'].values()):.3f}. The defensible conclusion is that the naïve hedge costs nothing in utility "
    "terms, not that it adds much."
)

heading("5.8 Robustness", 2)
para(
    f"*Data conventions.* Re-running the original sample with same-contract returns and the flexible calendar gives "
    f"{B['WTI']['naive']}, {B['GBPUSD']['naive']}, {B['SP500']['naive']} and {B['GOLD']['naive']} wins for the naïve "
    f"hedge and, again, no significant test in favor of an estimated model. The conclusion does not depend on how roll "
    "weeks are treated. The level of effectiveness can. Applied to the weeks after June 2023, the paper's spliced "
    f"returns put the naïve hedge's 5% CVaR effectiveness for the S&P 500 at {sp_post_paper.loc['naive', k5]:.2f}, "
    f"against {sp_post_ours.loc['naive', k5]:.2f} with same-contract returns. With interest rates above 4%, each "
    f"quarterly roll adds about {gap_sp_post.mean() * 100:.1f}% to the spliced futures series, and these roll weeks "
    "become the short hedger's largest recorded “losses” although no hedger bears them. Studies that splice futures "
    "prices will understate hedging effectiveness whenever the futures curve is steep."
)
para(
    f"*Natural gas spot source.* Using FRED alone, which restricts the evaluation to April 2008 onward "
    f"({NGF['n']} weeks), the naïve hedge wins {NGF['naive']} of 12 scenarios and no test favors an estimated model. "
    "*Winter Storm Uri.* The two weeks of February 2021 in which the spot price spiked and fell back are by far the "
    f"largest natural gas returns in the sample. Without them the naïve hedge still wins "
    f"{int(NGU.loc['excluding Uri weeks', 'naive_wins'])} of 12 scenarios, the OLS hedge is still less effective in "
    f"{int(NGU.loc['excluding Uri weeks', 'ols_below_naive'])} of 12 and no test favors an estimated model, while the "
    f"share of variance removed by the naïve hedge rises from {NGU.loc['full sample', 'he_var_naive'] * 100:.0f}% to "
    f"{NGU.loc['excluding Uri weeks', 'he_var_naive'] * 100:.0f}%. The natural gas result does not rest on that episode. "
    f"*Bitcoin spot source.* The CME reference rate is fixed in the London afternoon, several hours before the futures "
    f"settle. With Bloomberg's closing Bitcoin price the naïve hedge's effectiveness rises to between "
    f"{btc_x.loc['naive'].min():.2f} and {btc_x.loc['naive'].max():.2f}, and it wins {XBT['naive']} of 12 scenarios with "
    "no significant test against it. The ranking is the same; the level depends on timing, as it does for GBP/USD and gold."
)
ai = R.ai.set_index("weeks")
para(
    "*AI-concentration weeks.* Our proposal listed this as an optional check. It raised the possibility that the S&P 500's recent tail risk, which is driven "
    "by a small number of AI-linked stocks, might behave differently. As a brief check we flagged the worst 10% of weeks (Bloomberg total-return data) "
    f"for the iShares Semiconductor ETF between July 2023 and November 2026 ({int(ai.loc['AI-stress weeks', 'n'])} weeks, "
    f"with an average S&P 500 return of −{abs(ai.loc['AI-stress weeks', 'spx_mean']) * 100:.1f}%). They include the week of "
    "the DeepSeek sell-off of January 27, 2025. In those weeks the "
    f"naïve hedge removed {ai.loc['AI-stress weeks', 'naive_he'] * 100:.1f}% of the squared S&P 500 return, against "
    f"{ai.loc['Other weeks', 'naive_he'] * 100:.1f}% in other weeks, and no estimated model differed from it by more "
    f"than {max(abs(ai.loc['AI-stress weeks', f'{k}_he'] - ai.loc['AI-stress weeks', 'naive_he']) for k in est) * 100:.1f} "
    "percentage points. Index concentration changes what drives the S&P 500, but not "
    "how closely its futures track it."
)

# ------------------------------------------------------------------ 6 discussion

heading("6. Discussion and Limitations")
para(
    "Three alternative readings of the evidence deserve attention. The first is that the tests simply lack power, so "
    "that “not significantly better” means little. The paper's test does lack power here, because it treats two highly "
    "correlated series as independent. The paired test removes that weakness, and it moves the evidence toward the naïve "
    "hedge, not away from it. The second is that the estimated models are poor models. The in-sample results argue "
    "against this for three of the five. Evaluated on the weeks they were fitted to, the semivariance, HS and OLS hedges "
    f"are more effective than the naïve hedge in {IS_AHEAD['sv']}, {IS_AHEAD['hs']} and {IS_AHEAD['ols']} of the 72 "
    f"market–scenario pairs. The Cornish–Fisher hedge is ahead in only {IS_AHEAD['cfe']}, so its out-of-sample losses "
    "may owe something to the approximation as well as to noise. The copula hedge is ahead in "
    f"{IS_AHEAD['copula']}: it under-hedges by construction, in-sample and out-of-sample, and its failure is one of "
    "specification. The third is "
    "that a 52-week window is too short. We cannot rule this out. Our evidence is for a 52-week window only. We left the "
    "comparison of window lengths out when we narrowed the project in response to the feedback on our initial proposal, and the paper, whose method section mentions a 260-week window, reports results "
    "for 52 weeks only. A longer window would reduce noise in the estimates but would also respond more slowly to a "
    "change in the spot–futures relation, so the direction of the effect is not obvious. It is the first extension "
    "we would make, and it is also the direct test of our explanation: if estimation error is the cause, longer windows "
    "should reduce the noise in Table 8 and narrow the naïve hedge's lead. Our claim is therefore limited to this: with "
    "one year of weekly data, the results match what estimation error predicts in every respect we examined."
)
para(
    "The results should be read with six limitations in mind. Our spot series for GBP/USD and gold are not the paper's, "
    "so hedging-effectiveness levels for those markets are not comparable with the published ones. The post-2023 sample "
    "and the Bitcoin sample are short, and conclusions at the 1% level rest on two to four observations. Hedging "
    "effectiveness for natural gas and Bitcoin depends on which spot price is hedged; a firm exposed to a monthly index "
    "price would see a different basis from one exposed to Henry Hub daily spot. Our significance tests resample weeks independently, which ignores the "
    "clustering of volatile weeks and probably makes the counts of significant paired tests somewhat too large. We "
    "follow the paper's six models and do not consider dynamic hedge ratios, such as those from GARCH models. "
    "Finally, we study futures only. "
    "Options and other non-linear hedges address tail risk directly and are outside the scope of this project."
)

heading("7. Conclusion")
para(
    "This report asked whether the naïve hedge is still hard to beat for tail risk. It is. Rebuilding Cao and Conlon's "
    "(2025) study from raw data, we reach their central result for 1990 to June 2023: in each of the four markets the "
    "naïve hedge is the most effective model in at least as many scenarios as any estimated model, and the paper's test "
    "never favors an estimated model. The levels of effectiveness match the paper's for WTI and the S&P 500; for GBP/USD "
    "and gold ours are higher, because our spot prices come from a different source."
)
para(
    "Three more years of data and two new markets do not change the test result. From July 2023 to November 2026, and in "
    "Bitcoin and natural gas, the paper's test again never favors an estimated model. The scenario counts are less "
    "uniform. In the S&P 500, where every model removes nearly all of the risk, the OLS hedge wins more scenarios than "
    "the naïve hedge once the new weeks are included, and in the weeks after June 2023 the paired test finds the OLS and "
    "Cornish–Fisher hedges significantly better in the 10% downside scenarios, in every case by less than "
    f"{np.ceil(max(sp_full_margin, sp_post_margin) * 100) / 100:.2f} in effectiveness. Both hypotheses are "
    "supported as we stated them: no estimated model significantly and consistently outperforms the naïve hedge. The "
    "significance tests are on VaR-type quantiles; CVaR and semivariance are compared by effectiveness only. Our "
    f"paired test takes the result one step further than the paper. In {N_DIST_PAIR95} of the {N_DIST} distinct "
    f"original-sample comparisons ({N_NOCOP_PAIR95} of {N_NOCOP} without the copula model) the naïve hedge is not merely as good as the estimated model but significantly better, "
    "most often against the historical-simulation, Cornish–Fisher and copula models."
)
para(
    "The pattern of results is the one that estimation error predicts. A hedge ratio fitted to the tail of one "
    "year of weekly data rests on a handful of observations. It moves sharply from week to week, it works on the weeks "
    "it was fitted to and not on the weeks that follow, and it costs more to trade. The naïve ratio has none of these "
    "problems because it is not estimated. Put as a trade-off between bias and variance, the naïve hedge accepts a "
    "small, fixed error, because the best ratio is close to one in every market we study, in exchange for removing an "
    "estimation error that is, for the tail-risk models, many times larger. One check did not fit: in Bitcoin the OLS "
    "ratio is slightly less noisy than the naïve hedge is biased. These findings are for a 52-week estimation window."
)
para(
    "Basis risk, the main counterargument, does not rescue the estimated models. A volatile basis favors them in gold, "
    "but in natural gas, where spot and futures prices are least closely linked, the naïve hedge has its clearest lead. "
    f"Two cautions apply. That lead is relative: futures remove only {ng_var.loc['naive'].iloc[0] * 100:.0f}% of the "
    "variance of natural gas spot returns, so every hedge there is weak and the naïve hedge is the best of them. And "
    f"the Bitcoin evidence is thinner: the naïve hedge wins {D['BTC']['naive']} of 12 scenarios in a sample of "
    f"{D['BTC']['n']} weeks, although it is the market where a fixed ratio of one is furthest from the best ratio."
)
para(
    "The replication also produced a point of method. The paper's futures returns appear to be spliced across "
    "contracts, which counts the price gap at each roll as a return. When the futures curve is steep this makes a hedge "
    f"look worse than it is: after June 2023 it lowers the measured 5% CVaR effectiveness of the naïve hedge for the "
    f"S&P 500 from {sp_post_ours.loc['naive', k5]:.2f} to {sp_post_paper.loc['naive', k5]:.2f} (Section 5.8). Studies of "
    "hedging effectiveness should compute each futures return on a single contract."
)
para(
    "For a risk manager the lesson is that a hedge-ratio model is only as good as its inputs. For weekly tail risk "
    "estimated on a one-year window those inputs are too noisy to help. Where a liquid futures contract exists on the "
    "asset being hedged, the one-for-one hedge is the sensible default, and the case for replacing it has to be made out "
    "of sample and net of trading costs. Effort is better spent on the basis itself: choosing the contract, matching "
    "the timing of the exposure, and recognizing, as in natural gas, when the instrument cannot remove the risk at any "
    "ratio."
)

# ------------------------------------------------------------------ contributions and use of AI

heading("Group Member Contributions")
para(
    "Each member was responsible for a distinct part of the analysis and for the corresponding parts of this report "
    "and of the presentation, as set out in our revised proposal. The literature review, the discussion and the "
    "conclusion were written jointly. Methodology decisions were made together and recorded in the decision log."
)
para("**Hina Tomar.** Bloomberg and FRED data for the six markets; the rolled futures series; the naïve, OLS and "
     "historical-simulation hedges; the extension of the sample to 2026 (H1). Wrote the data and core replication "
     "parts.", after=3)
para("**Kavin Dhanasekaran.** The Cornish–Fisher, Clayton copula and semivariance hedges; hedge-ratio stability; the "
     "in-sample versus out-of-sample comparison (estimation error). Wrote the model and estimation-error parts.", after=3)
para("**Sai Kishore.** The evaluation framework (hedging effectiveness, the Wilcox test and utility); the basis-risk "
     "and CFNAI analysis; Bitcoin and natural gas (H2) and the stress episodes. Wrote the evaluation and new-market "
     "parts.")

heading("Use of AI Tools")
para(
    "We used Claude, an AI assistant made by Anthropic, throughout this project, through its coding tool Claude Code. "
    "It wrote and tested most of the Python code under our direction, helped audit the data, ran the analysis, and "
    "drafted and edited the text of this report. The team chose the paper, the hypotheses and the research design, "
    "made the methodology decisions recorded in the decision log (audit/METHODOLOGY_DECISION_LOG.md), and reviewed "
    "the code, the results and the text. We take responsibility for all content, including any errors."
)

# ------------------------------------------------------------------ references

heading("References")
REFS = [
    "Aquilina, M., Lombardi, M., Schrimpf, A., & Sushko, V. (2024). *The market turbulence and carry trade unwind of August 2024* (BIS Bulletin No. 90). Bank for International Settlements. https://www.bis.org/publ/bisbull90.htm",
    "Basel Committee on Banking Supervision. (2019). *Minimum capital requirements for market risk*. Bank for International Settlements. https://www.bis.org/bcbs/publ/d457.htm",
    "Bloomberg L.P. (2026). *Bloomberg Terminal* [Spot and futures price data]. Accessed through New York University.",
    "Cao, M., & Conlon, T. (2025). Tail risk hedging: The superiority of the naïve hedging strategy. *Journal of Futures Markets, 45*(8), 977–1005. https://doi.org/10.1002/fut.22602",
    "Cao, Z., Harris, R. D. F., & Shen, J. (2010). Hedging and value at risk: A semi-parametric approach. *Journal of Futures Markets, 30*(8), 780–794. https://doi.org/10.1002/fut.20440",
    "Clayton, D. G. (1978). A model for association in bivariate life tables and its application in epidemiological studies of familial tendency in chronic disease incidence. *Biometrika, 65*(1), 141–151. https://doi.org/10.1093/biomet/65.1.141",
    "Conlon, T., & Cotter, J. (2013). Downside risk and the energy hedger’s horizon. *Energy Economics, 36*, 371–379. https://doi.org/10.1016/j.eneco.2012.09.012",
    "Cotter, J., & Hanly, J. (2006). Reevaluating hedging performance. *Journal of Futures Markets, 26*(7), 677–702. https://doi.org/10.1002/fut.20212",
    "DeMiguel, V., Garlappi, L., & Uppal, R. (2009). Optimal versus naive diversification: How inefficient is the 1/N portfolio strategy? *Review of Financial Studies, 22*(5), 1915–1953. https://doi.org/10.1093/rfs/hhm075",
    "Ederington, L. H. (1979). The hedging performance of the new futures markets. *Journal of Finance, 34*(1), 157–170. https://doi.org/10.1111/j.1540-6261.1979.tb02077.x",
    "Federal Energy Regulatory Commission (FERC) & North American Electric Reliability Corporation (NERC). (2021). *The February 2021 cold weather outages in Texas and the South Central United States* [Staff report]. https://www.ferc.gov/media/february-2021-cold-weather-outages-texas-and-south-central-united-states-ferc-nerc-and",
    "Federal Reserve Bank of St. Louis. (2026). *Federal Reserve Economic Data (FRED)*: series CFNAI, DHHNGSP and DCOILWTICO [Data sets]. https://fred.stlouisfed.org",
    "Gensler, G. (2024, January 10). *Statement on the approval of spot bitcoin exchange-traded products*. U.S. Securities and Exchange Commission. https://www.sec.gov/newsroom/speeches-statements/gensler-statement-spot-bitcoin-011023",
    "Harrell, F. E., & Davis, C. E. (1982). A new distribution-free quantile estimator. *Biometrika, 69*(3), 635–640. https://doi.org/10.1093/biomet/69.3.635",
    "Harris, R. D. F., & Shen, J. (2006). Hedging and value at risk. *Journal of Futures Markets, 26*(4), 369–390. https://doi.org/10.1002/fut.20195",
    "International Monetary Fund. (2025). *Global financial stability report: Enhancing resilience amid uncertainty* (April 2025). https://www.imf.org/en/Publications/GFSR/Issues/2025/04/22/global-financial-stability-report-april-2025",
    "Wang, Y., Wu, C., & Yang, L. (2015). Hedging with futures: Does anything beat the naïve hedging strategy? *Management Science, 61*(12), 2870–2889. https://doi.org/10.1287/mnsc.2014.2028",
    "Wilcox, R. R., Erceg-Hurn, D. M., Clark, F., & Carlson, M. (2014). Comparing two independent groups via the lower and upper quantiles. *Journal of Statistical Computation and Simulation, 84*(7), 1543–1551. https://doi.org/10.1080/00949655.2012.754026",
]
for r in REFS:
    reference(r)

# ------------------------------------------------------------------ appendices

page_break()
TABLE_PLACE[0] = "H"
heading("Appendix A. Full Out-of-Sample Results")
para("Each table reports tail-risk hedging effectiveness for the 12 scenarios, with the p-value of the Wilcox et al. "
     "(2014) test against the naïve hedge in parentheses. The best model in each column is in bold. Columns 1–6 are "
     "downside risk and columns 7–12 upside risk. Tables 12 to 17 are the main results: the replication for the four "
     "original markets and the full sample for Bitcoin and natural gas. Tables 18 to 21 give the four original markets "
     "over the whole period, January 1990 to November 2026, in the same-contract setting; Panel C of Table 5 summarizes "
     "them. All ten follow the layout of the paper's Table 5. Tables 22 to 24 supplement them: Table 22 is the "
     "counterpart of the paper's Table 9, Table 23 breaks down our paired test by model, and Table 24 is the counterpart "
     "of the paper's Table 6.", 10)
FULL_H1 = [("ours", m, "full") for m in H1]
for st, m, sm in MAIN + FULL_H1:
    g, pv = R.grid(st, m, sm), R.grid(st, m, sm, val="p_wilcox")
    best = g.idxmax()
    rows, bold = [], set()
    for model in MODELS:
        for j, c in enumerate(COLS):
            if best[c] == model:
                bold.add((len(rows), j + 1))
        rows.append([label(model)] + [fmt(g.loc[model, c]) for c in COLS])
        if model != "naive":
            rows.append([""] + [f"({pv.loc[model, c]:.2f})" for c in COLS])
    period = ("January 1990 to June 2023, paper setting" if sm == "original" else
              "January 1990 to November 2026, same-contract setting" if m in H1 else "full sample, same-contract setting")
    table(f"{L[m]}: hedging effectiveness and p-values, {period} ({R.n(st, m, sm):,} weeks)", [""] + COL_LABELS, rows,
          [0.98] + [0.46] * 12, size=7.5, bold=bold)

rows = [[L[m]] + [str(int(v)) for v in R.wins(st, m, sm, mode="is")] for st, m, sm in MAIN]
table("Scenarios (of 12) won by each model when the ratios are evaluated in-sample",
      ["Market", "Naïve", "OLS", "HS", "CFE", "Copula", "Semivariance"], rows, [1.4] + [0.85] * 6,
      note="Each week's ratio is estimated on the 52 weeks ending in that week. Samples as in Table 7. The out-of-sample "
           "counts are in Panels A and D of Table 5.")
rows, tot_k, tot_n = [], {k: 0 for k in MODELS if k != "naive"}, {k: 0 for k in MODELS if k != "naive"}
for m in H1:
    x = distinct_frame("paper", m, "original")
    cells = []
    for k in tot_k:
        y = x[x.model == k]
        tot_k[k] += int((y.p_paired > 0.95).sum())
        tot_n[k] += len(y)
        cells.append(f"{int((y.p_paired > 0.95).sum())} of {len(y)}")
    rows.append([L[m]] + cells + [f"{int((x.p_paired > 0.95).sum())} of {len(x)}"])
rows.append(["All four markets"] + [f"{tot_k[k]} of {tot_n[k]}" for k in tot_k] + [f"{sum(tot_k.values())} of {sum(tot_n.values())}"])
assert sum(tot_k.values()) == N_DIST_PAIR95 and sum(tot_n.values()) == N_DIST
table("Distinct paired tests in which the naïve hedge is significantly better at the 5% level, by model, January 1990 to June 2023",
      ["Market", "OLS", "HS", "CFE", "Copula", "Semivariance", "All models"], rows, [1.4] + [0.85] * 6,
      note="Paper setting. OLS and semivariance have 6 distinct tests per market because their ratios do not depend on the "
           "risk measure; the other models have 12. No distinct test finds an estimated model significantly better.")

rows = []
for _, m, _ in MAIN:
    pv_, ps_ = PAPER_OLS_VAR_HE.get(m), PAPER_SEMI.get(m)
    both = lambda ours, paper: f"{ours:.4f} / {paper:.3f}" if paper is not None else f"{ours:.4f}"   # noqa: E731
    rows.append([L[m], f"{VAR[m]['naive']:.4f}", both(VAR[m]["ols"], pv_)]
                + [both(SEMI[m][k], ps_[k] if ps_ else None) for k in ("naive", "ols", "sv")])
table("Share of variance and of downside semivariance removed, out-of-sample: naïve, OLS and semivariance hedges",
      ["Market", "Variance: naïve", "Variance: OLS", "Semivariance: naïve", "Semivariance: OLS", "Semivariance: SV hedge"],
      rows, [1.2, 0.95, 1.2, 1.25, 1.2, 1.3],
      note="Samples as in Table 7. Where a cell has two values, the second is the paper's (its Table 5 for variance, its "
           "Table 6 for semivariance). Semivariance is the mean squared loss below zero of the short hedger's return. "
           "The semivariance hedge is the model that minimizes it in the estimation window.")

heading("Appendix B. Data, Code and Reproducibility")
para(
    "All data, code and results are in the project repository (github.com/HT05-S/Naive-Hedging-Tail-Risk). The raw "
    "Bloomberg and FRED files are stored unchanged, with their checksums verified by an automated test. Six scripts "
    "reproduce every number in this report from those files: the two weekly datasets "
    "(audit/stage1b_remediation.py and scripts/build_paper_dataset.py), the hedge ratios (scripts/run_hedges.py), the "
    "result tables (scripts/make_tables.py) and the figures and this document (scripts/make_figures.py and "
    "scripts/make_report.py). The copula simulation uses a fixed random seed. The data audit, the log of methodology "
    "decisions and the note on the paper's data conventions are in the audit folder.", 10)
para(
    "Implementation choices not specified in the paper: quantiles use linear interpolation between order statistics; "
    "CVaR is the mean of the observations at or beyond the quantile; semivariance uses a target return of zero; the "
    "Clayton parameter is estimated by maximum likelihood on ranks; and the same 10,000 uniform draws are used in every "
    "window so that changes in the copula hedge ratio reflect changes in the data. Hedge ratios are restricted to the "
    f"range 0 to 2. The Cornish–Fisher ratio sits at one of these limits in fewer than {max(at_limit(st, m) for st, m, _ in MAIN if m != 'NATGAS') * 100:.1f}% "
    f"of weeks in five markets and in {at_limit('ours', 'NATGAS') * 100:.0f}% of weeks in natural gas.", 10)

# ------------------------------------------------------------------ Appendix C (typeset in the PDF only)

heading("Appendix C. Mathematical Details of the Models and Tests")


def fill(block, **values):
    for k, v in values.items():
        block = block.replace(f"@{k}@", str(v))
    assert "@" not in block, block[block.index("@") - 40: block.index("@") + 40]
    return block


latex_only(r"""\begingroup\small
This appendix states the hedge-ratio models, the risk measures, the evaluation and the significance tests in the form in which our code implements them (\texttt{src/hedging/models.py}, \texttt{evaluate.py} and \texttt{analysis.py}). Equation numbers continue from the main text. Where a formula is the paper's, the paper's equation number is given. The decomposition in C.5, the paired bootstrap in C.6 and the cost example in C.7 are our additions; the rest restates the paper's method.

\subsection*{C.1 Returns and hedged returns}

Let $P^S_t$ and $P^F_t$ denote the spot and futures prices at weekly observation $t$. Weekly returns are logarithmic:
\begin{equation}
s_t = \ln\frac{P^S_t}{P^S_{t-1}}, \qquad f_t = \ln\frac{P^F_t}{P^F_{t-1}} .
\end{equation}
In the same-contract setting both futures prices belong to the same contract, so a roll never enters a return. A short hedger (long spot, short futures) and a long hedger (short spot, long futures) earn
\begin{equation}
y^{\mathrm{short}}_t(b) = s_t - b f_t, \qquad y^{\mathrm{long}}_t(b) = -s_t + b f_t = -y^{\mathrm{short}}_t(b),
\end{equation}
the paper's equations 1 and 2. Both kinds of risk can therefore be measured as the lower tail of one series, $x_t = y_t$ for downside risk and $x_t = -y_t$ for upside risk. This is why the upside columns of the tables are labelled 90\%, 95\% and 99\%: they are the 10\%, 5\% and 1\% lower tails of $-y$. With log returns, $y$ is a close approximation to the weekly return on the hedged position. The stress-episode table converts a log return $r$ to a simple return, $\exp(r) - 1$.

\subsection*{C.2 Risk measures on a sample}

For a sample $x_1,\ldots,x_n$ sorted in ascending order, $x_{(1)} \le \cdots \le x_{(n)}$, the $\alpha$-quantile is interpolated linearly between neighbouring order statistics:
\begin{equation}\label{eq:quantile}
h = (n-1)\alpha, \qquad k = \lfloor h \rfloor, \qquad \hat q_\alpha = x_{(k+1)} + (h-k)\big(x_{(k+2)} - x_{(k+1)}\big).
\end{equation}
VaR and CVaR are reported as positive losses. CVaR is the mean of the observations at or below the quantile, and semivariance is the mean squared shortfall below a target return of zero (the paper's equation 11):
\begin{equation}\label{eq:risk}
\widehat{\mathrm{VaR}}_\alpha = -\hat q_\alpha, \qquad \widehat{\mathrm{CVaR}}_\alpha = -\frac{1}{k+1}\sum_{i=1}^{k+1} x_{(i)}, \qquad \widehat{\mathrm{SV}} = \frac{1}{n}\sum_{t=1}^{n} \min\{x_t, 0\}^2 .
\end{equation}
\par\endgroup""",
           "Appendix C states the hedge-ratio models, the risk measures, the evaluation and the significance tests as "
           "formulas. It is typeset in the PDF version of this report and is not reproduced in this Word version, "
           "apart from the table below.")

W = 52
rows = []
for a in (0.10, 0.05, 0.01):
    h = (W - 1) * a
    k = int(np.floor(h))
    ordinal = lambda i: f"{i}{'st' if i == 1 else 'nd' if i == 2 else 'rd' if i == 3 else 'th'}"   # noqa: E731
    rows.append([f"{a * 100:.0f}%", f"{h:.2f}", f"between the {ordinal(k + 1)} and {ordinal(k + 2)} smallest", str(k + 1)])
table("How many weeks the tail estimates use in a 52-week estimation window",
      ["Tail level ⟦\\alpha‖α⟧", "⟦h = 51\\alpha‖h = 51α⟧", "VaR is interpolated", "Weeks averaged by CVaR"], rows,
      [1.2, 1.0, 2.6, 1.7], note="A 1% CVaR estimated on 52 weeks is the single worst week of the window.")

latex_only(fill(r"""\begingroup\small
The table makes the source of instability concrete. The ratio that minimizes 1\% CVaR in a 52-week window is the ratio that makes the single worst hedged week of the past year as mild as possible. When that week leaves the window, the ratio is re-fitted to a different week.

\subsection*{C.3 The hedge-ratio models}

Every model except the naïve and OLS hedges minimizes its risk measure over the grid $\{0, 0.01, \ldots, 2\}$, as in equation (4). The objective for each model is as follows.

\textit{Naïve.} $b = 1$. Nothing is estimated.

\textit{OLS (minimum variance).} Setting the derivative of $\sigma^2(b)$ to zero gives the regression slope, the only model with a closed form:
\begin{equation}
\hat b^{\mathrm{OLS}} = \frac{\sum_i (f_i - \bar f)(s_i - \bar s)}{\sum_i (f_i - \bar f)^2} = \frac{\widehat{\mathrm{Cov}}(s,f)}{\widehat{\mathrm{Var}}(f)} .
\end{equation}
The same ratio serves all 12 scenarios, because it does not depend on the tail or the risk measure.

\textit{Historical simulation (HS).} $\rho$ is the empirical VaR or CVaR of equations \eqref{eq:quantile} and \eqref{eq:risk} applied to the 52 hedged returns $x(b)$. No distribution is assumed.

\textit{Cornish--Fisher expansion (CFE).} Let $\sigma$, $S$ and $K$ be the standard deviation, skewness and excess kurtosis of the 52 hedged returns at a given $b$, and $z = \Phi^{-1}(\alpha)$ the standard normal quantile. The expansion adjusts $z$ for skewness and kurtosis (the paper's equation 7):
\begin{equation}
z_{\mathrm{CF}} = z + \frac{(z^2-1)S}{6} + \frac{(z^3-3z)K}{24} - \frac{(2z^3-5z)S^2}{36}, \qquad \mathrm{VaR}^{\mathrm{CF}}_\alpha = -\sigma\, z_{\mathrm{CF}} .
\end{equation}
CVaR replaces each power of $z$ by the corresponding moment of a standard normal variable $Z$ in its lower $\alpha$-tail, $M_i = \mathrm{E}\big[Z^i \mid Z \le z\big]$ (the paper's equation 8):
\begin{equation}
M_1 = -\frac{\phi(z)}{\alpha}, \qquad M_2 = 1 - \frac{z\,\phi(z)}{\alpha}, \qquad M_3 = -\frac{(z^2+2)\,\phi(z)}{\alpha},
\end{equation}
\begin{equation}
\mathrm{CVaR}^{\mathrm{CF}}_\alpha = -\sigma\Big[M_1 + \frac{(M_2-1)S}{6} + \frac{(M_3-3M_1)K}{24} - \frac{(2M_3-5M_1)S^2}{36}\Big].
\end{equation}
With $S = K = 0$ both formulas reduce to the normal VaR and CVaR. For upside risk the skewness changes sign and the kurtosis is unchanged. As in the paper's equations, the weekly mean is omitted. The intuition for the instability of this model is that $S$ and $K$ are third and fourth moments estimated from 52 observations and are multiplied by powers of $z$. One extreme week can move them, and the ratio, by a large amount.

\textit{Clayton copula.} The dependence between spot and futures is modelled separately from their marginal distributions (Clayton, 1978). Ranks are converted to pseudo-observations, and the Clayton copula is
\begin{equation}
u_i = \frac{\operatorname{rank}(f_i)}{n+1}, \qquad v_i = \frac{\operatorname{rank}(s_i)}{n+1}, \qquad C_\theta(u,v) = \big(u^{-\theta} + v^{-\theta} - 1\big)^{-1/\theta}.
\end{equation}
Its density, and the maximum-likelihood estimate of the parameter from the pseudo-observations, are
\begin{equation}
c_\theta(u,v) = (1+\theta)\,(uv)^{-1-\theta}\big(u^{-\theta} + v^{-\theta} - 1\big)^{-2-1/\theta},
\end{equation}
\begin{equation}
\hat\theta = \operatorname*{arg\,max}_{0.001 \le \theta \le 60}\; \sum_{i=1}^{n} \ln c_\theta(u_i, v_i).
\end{equation}
We draw 10,000 pairs of independent uniforms $(u, w)$, the same draws in every window, and obtain the second coordinate by inverting the conditional distribution $\partial C_\theta(u,v)/\partial u$:
\begin{equation}
v = \Big[u^{-\theta}\big(w^{-\theta/(1+\theta)} - 1\big) + 1\Big]^{-1/\theta}, \qquad \tilde f = \hat F_f^{-1}(u), \qquad \tilde s = \hat F_s^{-1}(v),
\end{equation}
where the inverse marginals are the empirical quantile functions of the window. The ratio minimizes the historical-simulation VaR or CVaR of $\tilde s - b\tilde f$ over the 10,000 simulated weeks. The Clayton copula has lower-tail dependence $\lambda_L = 2^{-1/\theta}$ and no upper-tail dependence: it makes spot and futures fall together more tightly than they rise together. Its parameter is related to Kendall's rank correlation by $\tau = \theta/(\theta+2)$.

\textit{Semivariance (SV).} $\rho$ is the semivariance of equation \eqref{eq:risk} applied to $x(b)$, the paper's equation 11.

\subsection*{C.4 Out-of-sample evaluation and hedging effectiveness}

The ratio applied in week $t$ is estimated on weeks $t-52$ to $t-1$, so no information from week $t$ is used. In the in-sample variant of Section 5.4 the window is weeks $t-51$ to $t$. Over the $T$ evaluation weeks the hedged and unhedged series are
\begin{equation}
x^H_t = \pm\big(s_t - \hat b_t f_t\big), \qquad x^U_t = \pm s_t, \qquad t = 1,\ldots,T,
\end{equation}
with the plus sign for downside and the minus sign for upside risk, and hedging effectiveness is (the paper's equations 12 to 15)
\begin{equation}
\mathrm{HE}_\rho = 1 - \frac{\rho\big(x^H_1,\ldots,x^H_T\big)}{\rho\big(x^U_1,\ldots,x^U_T\big)}, \qquad \mathrm{HE}_{\mathrm{Var}} = 1 - \frac{\widehat{\mathrm{Var}}(y)}{\widehat{\mathrm{Var}}(s)} .
\end{equation}
The model with the highest HE in a scenario wins that scenario. Stress episodes contain only a few weeks, too few to estimate a mean, so their effectiveness uses uncentred second moments, $1 - \sum_t y_t^2 / \sum_t s_t^2$.

\subsection*{C.5 Bias against variance: when the naïve hedge wins}

Suppose that weekly returns have constant moments and that the estimated ratio is independent of the returns of the week in which it is applied, as it is out of sample. Averaging the penalty of equation (1) over the estimate gives the expected variance of the hedged position:
\begin{equation}
\mathrm{E}\big[\sigma^2(\hat b)\big] = \sigma^2(\beta) + \sigma^2(f)\,\mathrm{E}\big[(\hat b - \beta)^2\big], \qquad \sigma^2(1) = \sigma^2(\beta) + \sigma^2(f)\,(1-\beta)^2 .
\end{equation}
Comparing the two gives inequality (2). For OLS the sampling part of the mean squared error has a known form. Writing the regression as $s_t = a + \beta f_t + \varepsilon_t$, with $R^2$ the share of spot variance explained by futures, the slope estimated from $n$ weeks has
\begin{equation}\label{eq:se}
\mathrm{Var}\big(\hat b^{\mathrm{OLS}}\big) \approx \frac{\sigma^2(\varepsilon)}{n\,\sigma^2(f)} = \frac{\beta^2}{n}\cdot\frac{1-R^2}{R^2},
\end{equation}
because $\sigma^2(\varepsilon) = (1-R^2)\,\sigma^2(s)$ and $\beta^2\sigma^2(f) = R^2\sigma^2(s)$. With sampling error alone, the naïve hedge beats the OLS hedge in expectation when
\begin{equation}
(1-\beta)^2 < \frac{\beta^2}{n}\cdot\frac{1-R^2}{R^2} .
\end{equation}
The factor $(1-R^2)/R^2$ is what links basis risk to estimation error. A loose link between spot and futures can move $\beta$ away from one, which favors estimated ratios, but it also raises the noise of the estimate steeply. With $n = 52$, equation \eqref{eq:se} gives a standard error of the OLS ratio of about @SE_WTI@ for WTI ($R^2 = @R2_WTI@$) and about @SE_NG@ for natural gas ($R^2 = @R2_NG@$). These are standard errors under constant moments. Table 8 does not report them. Its noise columns are the variance of each ratio over time, which is larger because the best ratio itself changes: the standard deviations of the OLS ratio in Table 7 are @SD_WTI@ and @SD_NG@. For natural gas, whose $\beta$ is @BETA_NG@, the right-hand side is large on either measure while the left-hand side is essentially zero. Tail-risk objectives have no closed form, but their ratios rest on fewer effective observations (Table 25), so their noise term is larger.

\subsection*{C.6 The significance test and the meaning of the p-values}

Let $x^M$ and $x^N$ be the side-adjusted out-of-sample hedged returns of an estimated model and of the naïve hedge over the same $T$ weeks, and $Q_\alpha(\cdot)$ their lower $\alpha$-quantiles. A higher lower quantile means a smaller loss, so the one-sided hypotheses are
\begin{equation}
H_0:\; Q_\alpha(x^M) \le Q_\alpha(x^N) \qquad\text{against}\qquad H_1:\; Q_\alpha(x^M) > Q_\alpha(x^N),
\end{equation}
where $H_1$ states that the model has less tail risk. Following Wilcox et al. (2014), each quantile is estimated with the Harrell and Davis (1982) estimator, a weighted average of all order statistics:
\begin{equation}
\hat Q_\alpha = \sum_{i=1}^{T} W_i\, x_{(i)}, \qquad W_i = I_{i/T}(\kappa_1, \kappa_2) - I_{(i-1)/T}(\kappa_1, \kappa_2),
\end{equation}
\begin{equation}
\kappa_1 = (T+1)\,\alpha, \qquad \kappa_2 = (T+1)(1-\alpha),
\end{equation}
where $I_z(\kappa_1, \kappa_2)$ is the cumulative distribution function of the beta distribution. The weights form a smooth bump centred near the $(\alpha T)$-th order statistic. Averaging neighbouring order statistics in this way usually gives a smaller variance in the tail than a single order statistic. The test compares quantiles in every scenario, so a CVaR scenario compares the $\alpha$-quantiles of the hedged returns produced by the CVaR-minimizing ratio.

\textit{The bootstrap p-value.} For $r = 1,\ldots,R$, with $R = 2{,}000$, we resample weeks with replacement, re-estimate both quantiles and record their difference. The p-value is the share of resamples in which the model has the larger tail risk, with ties counted as one half:
\begin{equation}
D^*_r = \hat Q^*_{\alpha,r}(x^M) - \hat Q^*_{\alpha,r}(x^N), \qquad p = \frac{1}{R}\sum_{r=1}^{R}\Big(\mathbf{1}\{D^*_r < 0\} + \tfrac12\,\mathbf{1}\{D^*_r = 0\}\Big).
\end{equation}
The bootstrap distribution of $D^*$ is centred near the observed difference. A p-value below 0.10 means that fewer than 10\% of resamples favor the naïve hedge, which rejects $H_0$ at the 10\% level in favor of the model. A p-value near 0.5 means that the observed difference is close to zero relative to its sampling variation. A p-value above 0.5 means that the observed difference favors the naïve hedge. Because $1-p$ is the p-value of the reverse one-sided hypothesis, a paired p-value above 0.95 rejects, at the 5\% level, the hypothesis that the model is at least as good as the naïve hedge. Neither $p$ nor $1-p$ is the probability that a hypothesis is true.

Weeks are resampled one at a time, as if they were independent. Weekly returns are close to uncorrelated, but volatile weeks cluster, so the bootstrap probably understates the sampling variation of a tail quantile. The counts of significant results in this report should be read with that in mind.

\textit{Why pairing adds power.} The sampling variance of the difference of the two quantile estimates is
\begin{equation}
\mathrm{Var}\big(\hat D\big) = \mathrm{Var}\big(\hat Q_\alpha(x^M)\big) + \mathrm{Var}\big(\hat Q_\alpha(x^N)\big) - 2\,\mathrm{Cov}\big(\hat Q_\alpha(x^M), \hat Q_\alpha(x^N)\big).
\end{equation}
The independent bootstrap of Wilcox et al. (2014), designed for two independent groups, draws different weeks for the two series and so sets the covariance term to zero. Our two series come from the same weeks: the median correlation between a model's hedged returns and the naïve hedge's is @CORR_MED@, and @CORR_90@\% of the correlations exceed 0.9. Ignoring the covariance therefore overstates the variance of the difference, pulls p-values toward 0.5 and lowers power in both directions. The paired bootstrap uses the same resampled weeks for both series and keeps the covariance.

\textit{Many tests at once.} The paper's test is run @NDIST@ distinct times on the original sample. If it had its nominal size and no estimated model differed from the naïve hedge, about @EXP10@ of those tests would reject at the 10\% level. We observe none: the smallest p-value is @PMIN@ and the median is @PMED@. This is weaker evidence than it looks, for the reason just given. The independent bootstrap is conservative for correlated series, so it rejects less often than its nominal level in either direction. The absence of rejections shows that the paper's test finds nothing in favor of the estimated models, not that there is nothing to find. The paired test is the informative one, because it has power in both directions. Among the same @NDIST@ comparisons it finds @NPAIR05@ in which an estimated model is significantly better at the 5\% level and @NPAIR95@ in which the naïve hedge is (Table 23). The tests are not independent, because scenarios share weeks and models share ratios, so these counts are more variable than counts of independent tests. A Bonferroni correction for @NDIST@ tests would require a p-value beyond $0.05/@NDIST@ \approx @BONF@$, which 2,000 resamples cannot resolve, since their smallest step is 0.0005. What we can say is that in @NALL@ of the @NDIST@ distinct paired tests not one of the 2,000 resamples favored the model.

\subsection*{C.7 Mean--variance utility}

Following the paper's equation 16, the utility of a hedged position over $T$ weeks is
\begin{equation}
U = \bar y - c\sum_{t=2}^{T}\big|\hat b_t - \hat b_{t-1}\big| - \frac{\gamma}{2}\,\widehat{\mathrm{Var}}(y), \qquad \gamma = 6, \quad c = 0.0003 .
\end{equation}
The naïve hedge has no turnover. The cost term sums over all $T$ weeks, while the mean and variance are weekly, so the cost grows with the length of the sample. For the WTI historical-simulation hedge (5\% CVaR, downside, replication sample), the cost term is @HS_COST@, while the variance terms of that model and of the naïve hedge differ by only @HS_VAR@, in favor of the naïve hedge. The cost term is about 30 times larger. This is why Section 5.7 reads the utility comparison as mainly a statement about trading costs.

\subsection*{C.8 Basis volatility and economic regimes}

The naïve hedged return is exactly the change in the log basis, $y_t(1) = s_t - f_t$. Basis volatility in week $t$ is the standard deviation of this change over weeks $t-52$ to $t-1$, so it is known when the hedge is set. Section 5.5 splits the evaluation weeks at its median. Economic regimes use the CFNAI of the calendar month of each week. A negative value means growth below its historical trend, and the latest published value is carried forward for recent months. The CFNAI split is an after-the-fact classification of weeks, not a signal available in real time.
\par\endgroup""",
                SE_WTI=f"{se_ols('WTI'):.2f}", R2_WTI=f"{BN.loc['WTI', 'r2']:.2f}", SE_NG=f"{se_ols('NATGAS'):.2f}",
                R2_NG=f"{BN.loc['NATGAS', 'r2']:.2f}", SD_WTI=f"{sd('paper', 'WTI', 'ols'):.2f}",
                SD_NG=f"{sd('ours', 'NATGAS', 'ols'):.2f}", BETA_NG=f"{BN.loc['NATGAS', 'beta']:.3f}",
                CORR_MED=f"{np.median(CORR):.2f}", CORR_90=f"{(CORR > 0.9).mean() * 100:.0f}", NDIST=N_DIST,
                EXP10=f"{0.10 * N_DIST:.0f}", PMIN=f"{P_MIN:.2f}", PMED=f"{P_MED:.2f}", NPAIR05=N_PAIR05 if N_PAIR05 else "none", NPAIR95=N_DIST_PAIR95,
                BONF=f"{0.05 / N_DIST:.5f}", NALL=N_NO_RESAMPLE, HS_COST=f"{hs_cost:.4f}", HS_VAR=f"{hs_var_gap:.5f}",
                ))
assert 28 < hs_cost / hs_var_gap < 34

finish()
