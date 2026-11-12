"""Write the final report as a Word document.

    python scripts/make_report.py

Every number in the tables, and every number in the text that depends on our results, is read from
results/tables/ (written by scripts/make_tables.py). Figures come from results/figures/.
"""
from __future__ import annotations

import re
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
from hedging.evaluate import RISK_AVERSION  # noqa: E402
from hedging.models import MODELS  # noqa: E402
from hedging.report_tables import (COL_LABELS, COLS, H1, H2, PAPER_NAIVE, PAPER_NAIVE_WINS, PAPER_NAIVE_WINS_IS,  # noqa: E402
                                   PAPER_OLS_VAR_HE, Results, fmt, label)

OUT = ROOT / "report" / "FRE6123_Final_Report_Tomar_Dhanasekaran_Kishore.docx"
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


def add_runs(par, text, size=11, bold=False):
    """Text with **bold** and *italic* spans."""
    for part in re.split(r"(\*\*.+?\*\*|\*.+?\*)", text):
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
            set_font(p.add_run(str(text)), size, bold=(i == 0) or is_group or ((i - 1, j) in bold), italic=is_group)
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

# ------------------------------------------------------------------ title and abstract

p = para("Is the Naïve Hedge Still Hard to Beat?", 17, WD_ALIGN_PARAGRAPH.CENTER, after=2)
p.runs[0].bold = True
para("Tail-Risk Hedging with Futures, 1990–2026, with Evidence from Bitcoin and Natural Gas", 13,
     WD_ALIGN_PARAGRAPH.CENTER, after=10)
para("Hina Tomar, Kavin Dhanasekaran and Sai Kishore", 11.5, WD_ALIGN_PARAGRAPH.CENTER, after=2)
para("FRE 6123 Financial Risk Management, Fall 2026 · Group Project: Final Report", 10.5, WD_ALIGN_PARAGRAPH.CENTER, after=2)
para("Department of Finance and Risk Engineering, NYU Tandon School of Engineering", 10.5, WD_ALIGN_PARAGRAPH.CENTER, after=2)
para("November 13, 2026", 10.5, WD_ALIGN_PARAGRAPH.CENTER, after=12)

heading("Abstract")
para(
    "Cao and Conlon (2025) report that a one-for-one futures hedge reduces tail risk at least as well as five estimated "
    "hedge-ratio models in four markets between 1990 and June 2023. We rebuild their study from raw Bloomberg and FRED "
    "data with our own code and ask two questions: does the result survive an independent replication and three further "
    "years of data, and does it extend to Bitcoin and natural gas, two markets with fatter tails and a less stable link "
    "between spot and futures prices? It does. In the original sample the naïve hedge is the most effective model in "
    f"{A['WTI']['naive']}, {A['GBPUSD']['naive']}, {A['SP500']['naive']} and {A['GOLD']['naive']} of 12 tail-risk "
    "scenarios for WTI crude oil, GBP/USD, the S&P 500 and gold, and no estimated model beats it at the 10% significance "
    f"level in any of {60 * 4} tests. The same holds from July 2023 to November 2026 and for Bitcoin and natural gas. A "
    "paired version of the test, which has more power than the one used in the paper, strengthens the conclusion: the "
    f"naïve hedge is significantly better than the estimated model in {tot(A, 'pair95')} of the {60 * 4} original-sample "
    "comparisons. The evidence points to estimation error as the reason. Estimated hedge ratios move widely from week to "
    "week, they win in-sample and lose out-of-sample, and the naïve hedge has its largest advantage in natural gas, where "
    "the spot–futures relation is least stable."
)

# ------------------------------------------------------------------ 1 introduction

heading("1. Introduction")
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
    "the published results, and then extend them in time and across markets. Our thesis is that the naïve hedge is hard "
    "to beat because estimated hedge ratios are noisy, not because the estimated models are badly designed, and that this "
    "holds with more force, not less, where the spot–futures relation is unstable."
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
    "with error. Wang et al. (2015) carry the argument to futures hedging: across 24 markets, no minimum-variance model "
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
    "The argument for both hypotheses is estimation error. A 52-week window holds about five observations in its worst "
    "10% and one in its worst 1%, so a ratio fitted to the tail is fitted to a handful of weeks and will not carry over "
    "to the next week. The naïve ratio is not estimated and has no such error. If this is right, three things should be "
    "visible in the data: estimated ratios should vary widely over time, estimated models should win when evaluated "
    "in-sample, and their advantage should disappear out of sample."
)
para(
    "The counterargument is basis risk. A one-for-one hedge is optimal only if spot and futures prices move together "
    "one for one. Where they do not, an estimated ratio can adapt and the naïve ratio cannot. In Cao and Conlon's own "
    "Table 13 the OLS hedge removes slightly more variance than the naïve hedge when basis risk is above its median in "
    "three of the four markets. Bitcoin and "
    "natural gas are therefore the hard test: if the naïve hedge fails anywhere, it should fail there. Section 5.5 "
    "examines this directly."
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
    "Table 1 lists the six markets. Futures prices and contract calendars are from Bloomberg; spot prices are from "
    "Bloomberg and from the Federal Reserve Bank of St. Louis (FRED). All series are daily and were sampled weekly on "
    "Wednesdays, as in the paper. Returns are log price changes. The Chicago Fed National Activity Index (CFNAI) from "
    "FRED identifies periods of below-average growth."
)
table("Markets, sources and samples", ["Market", "Spot price", "Futures", "Sample", "Weekly returns"], rows,
      [1.05, 2.45, 1.45, 1.35, 0.7],
      note="Weekly returns are counts in our data setting (Section 3.1). The first 52 weeks of each market are used only "
           "to estimate the first hedge ratio.")
heading("3.1 Reconstructing the paper's data conventions", 2)
para(
    "The paper describes its data in one paragraph: weekly Wednesday prices, 1,728 observations, and futures that are "
    "“nearest to maturity, with a rollover to the subsequent contract occurring on the first day of the contract month.” "
    "It does not say how holidays are handled or how returns are computed in a week when the contract changes. We "
    "inferred both from its summary statistics."
)
para(
    "*Calendar.* There are 1,748 Wednesdays between January 3, 1990 and June 28, 2023. On 20 of them at least one of the "
    "markets was closed. Keeping only Wednesdays on which every market traded leaves exactly 1,728 dates, the paper's "
    "count. The paper therefore appears to drop holiday Wednesdays without replacement."
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
      note="Each cell shows our value, then the paper's. Futures are spliced under the paper's roll rule.")
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
    "two settings. The *paper setting* (strict Wednesdays, spliced returns) is used to replicate the original sample. "
    "The *same-contract setting* computes every futures return on a single contract and, when a Wednesday is missing, "
    "moves the observation for both legs to Tuesday or Monday. It is used for the extension to 2026 and for Bitcoin and "
    "natural gas, and as a robustness check on the replication. The choice matters most for natural gas, where the next "
    f"contract is on average {gap_ng.mean() * 100:.1f}% more expensive than the expiring one at the roll and the gap has "
    f"been as large as {gap_ng.abs().max() * 100:.0f}%; a spliced series would record these gaps as hedging losses."
)
para(
    "For natural gas we combine two spot sources. FRED's Henry Hub series is sparse before 2007, and Bloomberg's series "
    "is dated one trading day late between January 2020 and mid-March 2021. We confirmed the second problem with three "
    "tests on the raw files: in that window Bloomberg has no Monday prices, its prices match FRED's previous-day prices, "
    "and its daily changes correlate with the previous day's futures change. We use Bloomberg before April 2007 and FRED "
    "from then on, and every weekly return uses one source at both ends."
)

# ------------------------------------------------------------------ 4 method

heading("4. Methodology")
para(
    "A hedger who is long one unit of spot and short *b* units of futures earns *y* = *s* − *b*·*f* in a week, where *s* "
    "and *f* are the spot and futures returns and *b* is set at the end of the previous week. Downside risk is the lower "
    "tail of *y*. Upside risk, the concern of a hedger who is short spot and long futures, is its upper tail. Each week, "
    "each model in Table 3 chooses *b* using only the previous 52 weeks."
)
rows = [
    ["Naïve", "b = 1", "Nothing is estimated."],
    ["OLS", "Minimum variance", "Slope of spot on futures returns (Ederington, 1979)."],
    ["Historical simulation (HS)", "Minimum VaR or CVaR", "Empirical tail of the 52 hedged returns (Harris & Shen, 2006)."],
    ["Cornish–Fisher (CFE)", "Minimum VaR or CVaR", "Normal quantile adjusted for skewness and kurtosis (Cao et al., 2010)."],
    ["Copula", "Minimum VaR or CVaR", "Clayton copula with empirical marginals; 10,000 simulated weeks per window."],
    ["Semivariance", "Minimum semivariance", "Mean squared loss below zero."],
]
table("The six hedge-ratio models", ["Model", "Objective", "How the ratio is obtained"], rows, [1.75, 1.45, 3.3])
para(
    "The HS, CFE and copula models are estimated separately for VaR and CVaR at the 10%, 5% and 1% levels, for downside "
    "and upside risk, which gives 12 scenarios per market. The risk-minimizing ratio is found by a grid search from 0 to "
    "2 in steps of 0.01. Hedging effectiveness is the share of risk removed, HE = 1 − Risk(hedged) / Risk(unhedged), "
    "measured over all out-of-sample weeks with historical-simulation VaR and CVaR, and also with variance and "
    "semivariance (Cotter & Hanly, 2006)."
)
para(
    "To test whether an estimated model beats the naïve hedge we follow the paper and use the test of Wilcox et al. "
    "(2014): the relevant quantile of each hedged-return series is estimated with the Harrell and Davis (1982) estimator, "
    "and a percentile bootstrap gives a one-sided p-value for the hypothesis that the model has lower tail risk. A small "
    "p-value favors the model; a p-value above 0.5 means the naïve hedge had the lower tail risk in the sample. The test "
    "resamples the two series independently. That is conservative here, because the two series come from the same weeks "
    "and are highly correlated. We therefore add a *paired* version that resamples whole weeks. It has more power to "
    "detect a difference in either direction."
)
para(
    "Three further analyses address the reason for the result: an in-sample run in which each week's ratio is estimated "
    "on the 52 weeks ending in that week; splits of the evaluation weeks by basis volatility and by the sign of the "
    "CFNAI; and the opportunity cost of the naïve hedge in mean–variance utility, with risk aversion of 6 and a "
    "transaction cost of 0.03% of turnover, as in the paper. All code is in Python, is covered by automated tests, and "
    "is in the project repository (Appendix B)."
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


def score_rows(d, markets, ref=None):
    out = []
    for m in markets:
        r = d[m]
        out.append([L[m], f"{r['n']:,}"] + [str(r[k]) for k in MODELS] + [str(r["ind10"]), f"{r['ind_half'] * 100:.0f}%",
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
      rows, [0.9, 0.48, 0.45, 0.38, 0.35, 0.38, 0.58, 0.35, 0.55, 0.5, 0.75, 0.83], size=8.5, group_rows=groups,
      note="Columns Naïve to SV count the scenarios (of 12) in which the model has the highest tail-risk effectiveness. "
           "The last four columns count the 60 tests of an estimated model against the naïve hedge (5 models × 12 "
           "scenarios): the Wilcox et al. (2014) test with p below 0.10 (model better), the share with p above 0.5, and "
           "the paired test with p below 0.05 (model significantly better) and above 0.95 (naïve hedge significantly "
           "better). OLS and semivariance ratios do not depend on the risk measure, so some tests repeat.")
others = sum(A[m][k] for m in H1 for k in ("hs", "cfe", "copula"))
para(
    f"Panel A of Table 5 gives the main replication result. The naïve hedge is the most effective model in "
    f"{A['WTI']['naive']} of 12 scenarios for WTI, {A['GBPUSD']['naive']} for GBP/USD, {A['SP500']['naive']} for the S&P "
    f"500 and {A['GOLD']['naive']} for gold. The paper reports {PAPER_NAIVE_WINS['WTI']}, {PAPER_NAIVE_WINS['GBPUSD']}, "
    f"{PAPER_NAIVE_WINS['SP500']} and {PAPER_NAIVE_WINS['GOLD']}. As in the paper, OLS, the simplest estimated model, "
    f"takes nearly all the remaining scenarios; the three tail-specific models (HS, CFE and copula) together win "
    f"{others} of 48. When an estimated model is ahead, the margin is small: the largest gain over the naïve hedge in "
    f"any scenario is {max((R.grid('paper', m, 'original').drop('naive').max() - naive[m]).max() for m in H1):.3f}."
)
para(
    f"None of the {60 * 4} tests rejects in favor of an estimated model at the 10% level, and between "
    f"{min(A[m]['ind_half'] for m in H1) * 100:.0f}% and {max(A[m]['ind_half'] for m in H1) * 100:.0f}% of the p-values "
    "in each market are above 0.5, in line with the paper's statement that the majority are. The paired test goes "
    f"further. It also finds no case in which an estimated model is better at the 5% level, and in {tot(A, 'pair95')} of "
    f"{60 * 4} comparisons it finds the naïve hedge significantly better at the 5% level. The paper's conclusion that the "
    "alternatives are no better is, on this evidence, an understatement for most of them. H1 holds in the original "
    "sample. Appendix A gives the full tables."
)

heading("5.2 Persistence, July 2023 to November 2026 (H1)", 2)
para(
    f"Panel B evaluates the {C['WTI']['n']} weeks after the paper's sample ends, using same-contract returns. The naïve "
    f"hedge is the best model in {C['WTI']['naive']} of 12 scenarios for WTI, {C['GBPUSD']['naive']} for GBP/USD and "
    f"{C['GOLD']['naive']} for gold, and no estimated model beats it at the 10% level in any market under the paper's "
    f"test. The S&P 500 is the exception in the count, with {C['SP500']['naive']} wins, but the exception has little "
    f"content. Every model except the copula removes "
    f"{sp_post_ours.drop('copula').loc[:, 'down'].min().min() * 100:.0f}% or more of the S&P 500 downside tail in this "
    "period, so the ranking is decided in the third decimal place. The paired test flags "
    f"{C['SP500']['pair05']} of 60 S&P 500 comparisons at the 5% level, all for the OLS and CFE hedges in the 10% "
    "downside scenarios, and none in the other three markets; three in 240 is fewer than chance alone would produce. "
    "With 175 weeks the 1% tail holds two observations, so we place "
    "more weight on Panel C, which adds the new weeks to the original sample: the naïve hedge wins "
    f"{F['WTI']['naive']}, {F['GBPUSD']['naive']}, {F['SP500']['naive']} and {F['GOLD']['naive']} of 12 scenarios and "
    "is never significantly beaten. H1 holds through November 2026."
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
table("Bitcoin and natural gas: tail-risk hedging effectiveness by model, full sample",
      ["", "VaR 5%", "CVaR 5%", "CVaR 1%", "VaR 95%", "CVaR 95%", "CVaR 99%"], rows, [1.9] + [0.75] * 6, bold=bold,
      group_rows=groups, note="Same-contract setting, out-of-sample. The best model in each column is in bold. The first "
                              "three columns are downside risk; the last three are upside risk.")
ols_below = int((ng.loc["ols"] < ng.loc["naive"]).sum())
para(
    f"Table 6 and Panel D of Table 5 report the new markets. For Bitcoin the naïve hedge removes "
    f"{btc.loc['naive'].min() * 100:.0f}% to {btc.loc['naive'].max() * 100:.0f}% of tail risk and is the best model in "
    f"{D['BTC']['naive']} of 12 scenarios. The semivariance and HS hedges win most of the others, mainly for upside risk. "
    f"The sample is short: {D['BTC']['n']} weeks hold about four observations in the 1% tail. No estimated model beats "
    f"the naïve hedge at the 10% level (the smallest p-value is {D['BTC']['min_p']:.2f}), and the paired test finds none "
    f"better at the 5% level and the naïve hedge significantly better in {D['BTC']['pair95']} of 60 comparisons."
)
para(
    f"Natural gas is the more demanding case. The futures hedge is far less effective than in any other market: the "
    f"naïve hedge removes only {ng.loc['naive'].min() * 100:.0f}% to {ng.loc['naive'].max() * 100:.0f}% of tail risk and "
    f"{ng_var.loc['naive'].iloc[0] * 100:.0f}% of variance. Henry Hub spot is a price for gas delivered the next day, "
    "and weather can move it far from the futures price, which covers delivery over the following month. In the week of "
    f"Winter Storm Uri the spot price rose from ${uri.loc['2021-02-10', 'spot_price']:.2f} to "
    f"${uri.loc['2021-02-17', 'spot_price']:.2f} per million Btu and fell back to "
    f"${uri.loc['2021-02-24', 'spot_price']:.2f} a week later, while the front futures contract rose by about "
    f"{(np.exp(uri.loc['2021-02-17', 'fut_logret']) - 1) * 100:.0f}% and fell by about "
    f"{(1 - np.exp(uri.loc['2021-02-24', 'fut_logret'])) * 100:.0f}%. No hedge ratio protects against that. This is exactly the "
    "setting in which the counterargument of Section 2.3 expects estimated ratios to help. They do not: the naïve hedge "
    f"is the best model in {D['NATGAS']['naive']} of 12 scenarios, the OLS hedge is less effective than the naïve hedge "
    f"in {ols_below} of 12, no test favors an estimated model, and the paired test finds the naïve hedge "
    f"significantly better in {D['NATGAS']['pair95']} of 60 comparisons. H2 holds for both markets."
)

heading("5.4 Why: estimation error", 2)
para(
    "The three signs of estimation error set out in Section 2.3 are all present. First, estimated ratios are unstable. "
    "Figure 1 plots the weekly ratios that minimize 5% CVaR for WTI. The OLS and semivariance ratios stay close to one. "
    "The HS and CFE ratios, which are fitted to the tail of 52 observations, jump between about 0.5 and 1.5 as single "
    "extreme weeks enter and leave the window. Table 7 shows the same pattern in every market, and it is most pronounced "
    f"in natural gas, where even the OLS ratio has a standard deviation of {sd('ours', 'NATGAS', 'ols'):.2f}. The copula "
    f"ratio is stable but biased: it averages about {np.mean([mean_b(st, m, 'copula') for st, m, _ in MAIN]):.2f} for "
    "downside risk in our data, as in the paper, and so under-hedges systematically."
)
figure("fig1_hedge_ratios_wti.png", "Hedge ratios that minimize 5% CVaR (downside), WTI, 52-week rolling window, "
                                     "1991 to June 2023. The dashed line is the naïve ratio of one.", 5.6)
rows = []
for st, m, sm in MAIN:
    rows.append([L[m]] + [f"{mean_b(st, m, k):.2f} ({sd(st, m, k):.2f})" for k in MODELS if k != "naive"])
table("Hedge ratios that minimize 5% CVaR (downside): mean and standard deviation over time",
      ["Market", "OLS", "HS", "CFE", "Copula", "Semivariance"], rows, [1.3] + [1.02] * 5,
      note="Standard deviations in parentheses. Original sample for the first four markets (paper setting); full sample "
           "for Bitcoin and natural gas (same-contract setting). The naïve ratio is 1 with no variation.")
para(
    "Second, the estimated models win in-sample. Figure 2 counts the scenarios in which the naïve hedge is the best "
    "model when each ratio is evaluated on the weeks it was estimated on, and when it is applied to the following week. "
    f"In-sample the naïve hedge is best in {A_IS['WTI']}, {A_IS['GBPUSD']}, {A_IS['SP500']} and {A_IS['GOLD']} of 12 "
    f"scenarios in the four original markets and in {D_IS['BTC']} and {D_IS['NATGAS']} for Bitcoin and natural gas; the "
    "paper reports 1, 3, 3 and 3. The models are therefore not badly specified. They do find ratios that would have "
    "reduced tail risk further. Third, that advantage does not survive the step to the next week: out-of-sample, the "
    "best estimated model loses on average "
    f"{np.mean([is_gain(*k) for k in MAIN[:4]]):.3f} of effectiveness in the original markets relative to its in-sample "
    f"result, which is the whole of its in-sample lead over the naïve hedge ({np.mean([is_lead(*k) for k in MAIN[:4]]):.3f}). "
    f"In natural gas it loses {is_gain('ours', 'NATGAS', 'full'):.3f}, more than its in-sample lead of "
    f"{is_lead('ours', 'NATGAS', 'full'):.3f}."
)
figure("fig2_naive_wins_in_vs_out.png", "Scenarios (of 12) in which the naïve hedge has the highest tail-risk "
                                         "effectiveness, out-of-sample and in-sample.", 5.8)

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
table("Naïve and OLS hedges by basis volatility and by economic growth",
      ["Market", "Naïve wins (of 12)", "OLS wins (of 12)", "5% CVaR HE, naïve", "5% CVaR HE, OLS"], rows,
      [1.3, 1.3, 1.3, 1.3, 1.3], group_rows=groups,
      note="Out-of-sample. Basis volatility is the standard deviation of the weekly difference between spot and futures "
           "returns over the previous 52 weeks, split at its median. Original sample for the first four markets; full "
           "sample for Bitcoin and natural gas.")
bl = {m: (int(R.wins(st, m, sm, subset="basis_low")["naive"]), int(R.wins(st, m, sm, subset="basis_high")["naive"])) for st, m, sm in MAIN}
cf = {m: (int(R.wins(st, m, sm, subset="cfnai_below")["naive"]), int(R.wins(st, m, sm, subset="cfnai_above")["naive"])) for st, m, sm in MAIN}
gold_high = R.grid("paper", "GOLD", "original", subset="basis_high")
gold_margin = float((gold_high.drop("naive").max() - gold_high.loc["naive"]).max())
k5 = ("down", "CVaR", 0.05)
ngh = R.grid("ours", "NATGAS", "full", subset="basis_high")
para(
    "Table 8 tests the counterargument. If basis risk favored estimated ratios, the naïve hedge should win less often "
    "when the basis is volatile. Gold behaves this way: the naïve hedge wins "
    f"{bl['GOLD'][0]} of 12 scenarios in calm-basis weeks and {bl['GOLD'][1]} in volatile-basis weeks, where OLS and "
    f"the semivariance hedge are ahead, by at most {gold_margin:.3f} in effectiveness. This is the pattern in the "
    "paper's Table 13. It does not "
    f"generalize. For the S&P 500, Bitcoin and natural gas the naïve hedge wins more often when the basis is volatile "
    f"({bl['SP500'][1]}, {bl['BTC'][1]} and {bl['NATGAS'][1]} of 12) than when it is calm ({bl['SP500'][0]}, "
    f"{bl['BTC'][0]} and {bl['NATGAS'][0]}), and in volatile-basis weeks for natural gas the OLS hedge removes "
    f"{ngh.loc['ols', k5] * 100:.0f}% of the 5% CVaR against {ngh.loc['naive', k5] * 100:.0f}% for the naïve hedge. Our "
    "reading is that a volatile basis has two effects. It makes the best ratio differ from one, which helps estimated "
    "models, and it makes that ratio harder to estimate from 52 weeks, which hurts them. In the two new markets the "
    "second effect dominates."
)
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
    rows.append([e.replace("-", "–"), L[m], str(int(r["weeks"])), pct(r["unhedged_worst_week"]), pct(r["naive_worst_week"]),
                 f"{pct(r[f'{best}_worst_week'])} ({label(best)})", pct(min(r[f"{k}_worst_week"] for k in est))])
n_ahead = sum(np.exp(max(S.loc[k][f"{e}_worst_week"] for e in est)) - np.exp(S.loc[k]["naive_worst_week"]) > 0.02 for k in pick)
table("Worst weekly return of a long spot position in stress episodes: unhedged and hedged",
      ["Episode", "Market", "Weeks", "Unhedged", "Naïve hedge", "Best estimated model", "Worst estimated model"], rows,
      [1.75, 0.85, 0.5, 0.75, 0.8, 1.2, 0.9], size=8.5,
      note="Out-of-sample hedge ratios that minimize 5% CVaR. Simple weekly returns; a negative value is a loss. The "
           "best estimated model is known only after the fact.")
para(
    "Table 9 looks at the weeks that matter most. In the market-wide episodes the naïve hedge removes nearly all of the "
    "loss in the S&P 500 and most of it in WTI and Bitcoin. The best estimated model, which can be identified only "
    f"afterwards, is more than two percentage points ahead in {n_ahead} of the {len(pick)} cases. The column for the "
    "worst estimated model shows the other side of estimation. After the first weeks of the COVID crash the "
    "Cornish–Fisher ratio for WTI and the S&P 500 jumped to 2, the upper limit of our search grid, and the over-hedged "
    "position then lost heavily when prices rebounded. Two episodes show the limits of any futures hedge. In Winter Storm Uri "
    "the loss came from a spot price that the futures did not follow, and in the FTX collapse the naïve hedge removed "
    "less than half of the worst weekly loss in Bitcoin's reference rate. These are failures of the instrument, not of "
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
    "A fixed ratio could still be costly if it gave up return or added variance in ordinary weeks. Table 10 follows the "
    "paper's calculation and reaches the paper's result: the utility of the naïve hedge is higher than that of every "
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
    f"*Bitcoin spot source.* The CME reference rate is fixed in the London afternoon, several hours before the futures "
    f"settle. With Bloomberg's closing Bitcoin price the naïve hedge's effectiveness rises to between "
    f"{btc_x.loc['naive'].min():.2f} and {btc_x.loc['naive'].max():.2f}, and it wins {XBT['naive']} of 12 scenarios with "
    "no significant test against it. The ranking is the same; the level depends on timing, as it does for GBP/USD and gold."
)
ai = R.ai.set_index("weeks")
para(
    "*AI-concentration weeks.* The proposal raised the possibility that the S&P 500's recent tail risk, which is driven "
    "by a small number of AI-linked stocks, might behave differently. As a brief check we flagged the worst 10% of weeks "
    f"for the iShares Semiconductor ETF between July 2023 and November 2026 ({int(ai.loc['AI-stress weeks', 'n'])} weeks, "
    f"with an average S&P 500 return of −{abs(ai.loc['AI-stress weeks', 'spx_mean']) * 100:.1f}%). In those weeks the "
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
    "hedge, not away from it. The second is that the estimated models are poor models. The in-sample results rule this "
    "out for four of the five: they find better ratios when the answer is known. The copula model is the exception. It "
    "under-hedges by construction, in-sample and out-of-sample, and its failure is one of specification. The third is "
    "that a 52-week window is too short. We did not test longer windows, a restriction we accepted to narrow the "
    "project; the paper reports the same conclusion with 260 weeks. A longer window would reduce noise in the estimates "
    "but would also respond more slowly, and our stress-episode results suggest that slow-moving tail estimates are "
    "themselves a source of loss."
)
para(
    "The results should be read with four limitations in mind. Our spot series for GBP/USD and gold are not the paper's, "
    "so hedging-effectiveness levels for those markets are not comparable with the published ones. The post-2023 sample "
    "and the Bitcoin sample are short, and conclusions at the 1% level rest on two to four observations. Hedging "
    "effectiveness for natural gas and Bitcoin depends on which spot price is hedged; a firm exposed to a monthly index "
    "price would see a different basis from one exposed to Henry Hub daily spot. Finally, we study futures only. "
    "Options and other non-linear hedges address tail risk directly and are outside the scope of this project."
)
para(
    "For a risk manager the practical implication is narrow but useful. Where a liquid futures contract exists on the "
    "asset being hedged, a one-for-one hedge is a sound default for tail risk, and the case for replacing it with an "
    "estimated ratio has to be made out of sample and net of trading costs. Effort is better spent on the basis itself: "
    "choosing the contract, matching the timing of the exposure, and recognizing, as in natural gas, when the "
    "instrument cannot remove the risk at any ratio."
)

heading("7. Conclusion")
para(
    "We set out to test whether the naïve hedge is still hard to beat. An independent replication from raw data "
    "reproduces Cao and Conlon's (2025) central result for 1990 to June 2023: the naïve hedge is the most effective model "
    "in more scenarios than any alternative, and no alternative is significantly better. The result persists through "
    "November 2026 and extends to Bitcoin and natural gas, which supports both of our hypotheses. A more powerful paired "
    "test shows that the naïve hedge is in most cases significantly better than the tail-specific models, not merely "
    "indistinguishable from them."
)
para(
    "The explanation is estimation error. Hedge ratios fitted to the tail of a one-year window are unstable, they "
    "succeed only on the data they were fitted to, and they cost more to maintain. The counterargument that an unstable "
    "basis should favor estimated ratios holds for gold and fails where it matters most: in natural gas, the market with "
    "the weakest spot–futures link in our study, the naïve hedge has its clearest advantage. The contribution of a "
    "hedge-ratio model is limited by how well its inputs can be estimated, and for tail risk at a weekly horizon that "
    "limit is reached quickly."
)

# ------------------------------------------------------------------ references

heading("References")
REFS = [
    "Aquilina, M., Lombardi, M., Schrimpf, A., & Sushko, V. (2024). *The market turbulence and carry trade unwind of August 2024* (BIS Bulletin No. 90). Bank for International Settlements.",
    "Basel Committee on Banking Supervision. (2019). *Minimum capital requirements for market risk*. Bank for International Settlements.",
    "Bloomberg L.P. (2026). *Bloomberg Terminal* [Spot and futures price data]. Accessed through New York University.",
    "Cao, M., & Conlon, T. (2025). Tail risk hedging: The superiority of the naïve hedging strategy. *Journal of Futures Markets, 45*(8), 977–1005.",
    "Cao, Z., Harris, R. D. F., & Shen, J. (2010). Hedging and value at risk: A semi-parametric approach. *Journal of Futures Markets, 30*(8), 780–794.",
    "Conlon, T., & Cotter, J. (2013). Downside risk and the energy hedger’s horizon. *Energy Economics, 36*, 371–379.",
    "Cotter, J., & Hanly, J. (2006). Reevaluating hedging performance. *Journal of Futures Markets, 26*(7), 677–702.",
    "DeMiguel, V., Garlappi, L., & Uppal, R. (2009). Optimal versus naive diversification: How inefficient is the 1/N portfolio strategy? *Review of Financial Studies, 22*(5), 1915–1953.",
    "Ederington, L. H. (1979). The hedging performance of the new futures markets. *Journal of Finance, 34*(1), 157–170.",
    "Federal Energy Regulatory Commission (FERC) & North American Electric Reliability Corporation (NERC). (2021). *The February 2021 cold weather outages in Texas and the South Central United States* [Staff report].",
    "Federal Reserve Bank of St. Louis. (2026). *Federal Reserve Economic Data (FRED)*: series CFNAI, DHHNGSP and DCOILWTICO [Data sets].",
    "Gensler, G. (2024, January 10). *Statement on the approval of spot bitcoin exchange-traded products*. U.S. Securities and Exchange Commission.",
    "Harrell, F. E., & Davis, C. E. (1982). A new distribution-free quantile estimator. *Biometrika, 69*(3), 635–640.",
    "Harris, R. D. F., & Shen, J. (2006). Hedging and value at risk. *Journal of Futures Markets, 26*(4), 369–390.",
    "International Monetary Fund. (2025). *Global financial stability report: Enhancing resilience amid uncertainty* (April 2025).",
    "Wang, Y., Wu, C., & Yang, L. (2015). Hedging with futures: Does anything beat the naïve hedging strategy? *Management Science, 61*(12), 2870–2889.",
    "Wilcox, R. R., Erceg-Hurn, D. M., Clark, F., & Carlson, M. (2014). Comparing two independent groups via the lower and upper quantiles. *Journal of Statistical Computation and Simulation, 84*(7), 1543–1551.",
]
for r in REFS:
    p = para(r, 10, WD_ALIGN_PARAGRAPH.LEFT, after=3)
    p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Inches(0.3), Inches(-0.3)

# ------------------------------------------------------------------ appendices

doc.add_page_break()
heading("Appendix A. Full Out-of-Sample Results")
para("Each table reports tail-risk hedging effectiveness for the 12 scenarios, with the p-value of the Wilcox et al. "
     "(2014) test against the naïve hedge in parentheses. The best model in each column is in bold. Columns 1–6 are "
     "downside risk and columns 7–12 upside risk.", 10)
for st, m, sm in MAIN:
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
    period = "January 1990 to June 2023, paper setting" if sm == "original" else "full sample, same-contract setting"
    table(f"{L[m]}: hedging effectiveness and p-values, {period} ({R.n(st, m, sm):,} weeks)", [""] + COL_LABELS, rows,
          [0.98] + [0.46] * 12, size=7.5, bold=bold)

heading("Appendix B. Data, Code and Reproducibility")
para(
    "All data, code and results are in the project repository (github.com/HT05-S/Naive-Hedging-Tail-Risk). The raw "
    "Bloomberg and FRED files are stored unchanged, with their checksums verified by an automated test. Five scripts "
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

page_number_footer()
OUT.parent.mkdir(exist_ok=True)
doc.save(OUT)
print("report ->", OUT)
