"""Starter map from well-known SNPs to nutrition labels.

Illustrative and educational only. Not a medical report, not a diagnosis,
and not a supplement protocol. Confidence is only "low" or "medium".
Genotypes are the plus-strand letters 23andMe writes in the raw file.
"""
from __future__ import annotations

EDUCATIONAL = (
    "Illustrative only — not medical advice. This short map links markers that "
    "are often discussed in public nutrition research to plain-language labels. "
    "Effects are usually small, depend on ancestry and the rest of the diet, "
    "and are not a diagnosis or a reason to start supplements."
)

# when: plus-strand genotypes (order-insensitive) that highlight the label.
TRAITS: list[dict] = [
    {
        "rsid": "rs1801133",
        "gene": "MTHFR",
        "label": "Folate metabolism (C677T)",
        "confidence": "medium",
        "when": ["CT", "TT"],
        "focus_tags": ["folate"],
        "note": (
            "Often cited for MTHFR C677T. Biochemistry papers describe lower enzyme "
            "activity for TT than CC, with CT in between. That is not a folate "
            "prescription. When this is highlighted, the menu includes foods that "
            "contribute folate, such as leafy greens and lentils."
        ),
    },
    {
        "rsid": "rs1801131",
        "gene": "MTHFR",
        "label": "Folate metabolism (A1298C)",
        "confidence": "low",
        "when": ["CC"],
        "focus_tags": ["folate"],
        "note": (
            "A second MTHFR site, discussed less consistently than C677T. Only the "
            "CC call is flagged, and only as a weak educational note next to "
            "folate-containing foods."
        ),
    },
    {
        "rsid": "rs9939609",
        "gene": "FTO",
        "label": "Appetite and weight tendency",
        "confidence": "medium",
        "when": ["AA", "AT"],
        "focus_tags": ["appetite"],
        "note": (
            "One of the best-replicated common markers in BMI genome-wide studies. "
            "The A allele is associated with a higher average weight, largely through "
            "appetite, and the effect for one person is modest. A highlighted call "
            "tilts portions toward protein and vegetables. It does not say whether a diet will work."
        ),
    },
    {
        "rsid": "rs5082",
        "gene": "APOA2",
        "label": "Saturated-fat response",
        "confidence": "medium",
        "when": ["GG"],
        "focus_tags": ["sat_fat"],
        "note": (
            "Papers on APOA2 −265T>C report a higher average BMI for the CC genotype "
            "when saturated-fat intake is high. 23andMe reports the plus strand, where "
            "that call is GG (the gene is on the minus strand). Replication is narrower "
            "than a typical BMI genome-wide hit. When flagged, the menu uses olive oil, "
            "fish, and beans instead of a high-saturated-fat pattern."
        ),
    },
    {
        "rsid": "rs7903146",
        "gene": "TCF7L2",
        "label": "Carbohydrate and glycemic tendency",
        "confidence": "medium",
        "when": ["CT", "TT"],
        "focus_tags": ["fiber"],
        "note": (
            "The strongest common marker in type 2 diabetes genome-wide studies. The T "
            "allele is associated with higher average risk in many populations. This app "
            "does not assess diabetes risk. A highlighted call only prefers higher-fiber "
            "carbohydrate foods such as oats, beans, and lentils."
        ),
    },
    {
        "rsid": "rs4988235",
        "gene": "MCM6/LCT",
        "label": "Lactase persistence (European-ancestry marker)",
        "confidence": "medium",
        "when": ["GG"],
        "focus_tags": ["lactose_free"],
        "note": (
            "In many people of European ancestry, GG at rs4988235 is the plus-strand "
            "call discussed as lactase non-persistence (research papers often say CC, "
            "on the other strand). Other ancestries use different variants, so GG is "
            "not a universal lactose test, and it is not a symptom diary. When flagged, "
            "the menu skips cow's-milk yogurt."
        ),
    },
    {
        "rsid": "rs174547",
        "gene": "FADS1",
        "label": "Omega-3 and omega-6 conversion",
        "confidence": "medium",
        "when": ["CC"],
        "focus_tags": ["omega3"],
        "note": (
            "A meta-analysis of rs174547 links the minor C allele with lower delta-5 "
            "and delta-6 desaturase activity estimates and different blood fat levels. "
            "Only CC is flagged here. The menu then includes fish and walnuts, which "
            "already contain longer-chain omega-3s. This is not a measured fatty-acid level."
        ),
    },
    {
        "rsid": "rs762551",
        "gene": "CYP1A2",
        "label": "Caffeine metabolism",
        "confidence": "medium",
        "when": ["AC", "CC"],
        "focus_tags": ["caffeine_note"],
        "note": (
            "The A allele is widely described as the faster caffeine-metabolizer call "
            "and C as slower. Studies that connect this marker to coffee and heart risk "
            "do not agree. A highlighted call adds a moderation note. It does not add or "
            "remove a meal."
        ),
    },
    {
        "rsid": "rs2282679",
        "gene": "GC",
        "label": "Vitamin D status tendency",
        "confidence": "medium",
        "when": ["GG", "GT"],
        "focus_tags": ["vitamin_d"],
        "note": (
            "A genome-wide marker near the vitamin D binding-protein gene. The G allele "
            "is associated with lower average 25-hydroxyvitamin D in population studies. "
            "Sunlight, season, and supplements usually matter more than single foods. "
            "The menu only includes food sources such as salmon, sardines, and fortified "
            "soy milk — not a dose."
        ),
    },
    {
        "rsid": "rs7501331",
        "gene": "BCMO1",
        "label": "Beta-carotene conversion",
        "confidence": "low",
        "when": ["CT", "TT"],
        "focus_tags": ["carotenoid"],
        "note": (
            "A BCMO1 missense variant (often called A379V) reported in smaller studies "
            "to reduce conversion of beta-carotene toward vitamin A. Evidence is thinner "
            "than the genome-wide markers above. When flagged, the menu keeps orange and "
            "dark-green vegetables and does not claim a vitamin A deficiency."
        ),
    },
    {
        "rsid": "rs12934922",
        "gene": "BCMO1",
        "label": "Beta-carotene conversion (second site)",
        "confidence": "low",
        "when": ["AT", "TT"],
        "focus_tags": ["carotenoid"],
        "note": (
            "A second BCMO1 variant sometimes studied beside rs7501331. Findings are "
            "preliminary. The same vegetable pattern applies. This is not a reason to "
            "start vitamin A supplements."
        ),
    },
    {
        "rsid": "rs2187668",
        "gene": "HLA-DQ2.5",
        "label": "Celiac-associated HLA type (tag SNP)",
        "confidence": "medium",
        "when": ["CT", "TT"],
        "focus_tags": ["gluten_free"],
        "note": (
            "rs2187668 tags the HLA-DQ2.5 haplotype, which most people with celiac "
            "disease carry. Many carriers never develop celiac disease, and this is not "
            "a diagnosis; testing is done by a clinician. When highlighted, the diet "
            "builder hides wheat, barley and rye foods and keeps gluten-free grains."
        ),
    },
    {
        "rsid": "rs699",
        "gene": "AGT",
        "label": "Salt sensitivity (AGT M235T)",
        "confidence": "low",
        "when": ["GG"],
        "focus_tags": ["sodium"],
        "note": (
            "AGT M235T (G allele on the plus strand) is linked in some studies to "
            "higher angiotensinogen levels and blood-pressure response to salt. "
            "Findings are mixed. When highlighted, the diet builder hides portions "
            "with 460 mg or more of sodium."
        ),
    },
]


def _alleles(genotype: str) -> str:
    text = (genotype or "").strip().upper().replace(" ", "")
    letters = [ch for ch in text if ch in "ACGT"]
    if not letters or set(text) <= set("-0N"):
        return ""
    return "".join(sorted(letters))


def _public_row(entry: dict, genotype: str | None) -> dict:
    return {
        "rsid": entry["rsid"],
        "gene": entry["gene"],
        "label": entry["label"],
        "confidence": entry["confidence"],
        "note": entry["note"],
        "genotype": genotype or "",
        "focus_tags": list(entry["focus_tags"]),
    }


def summarize(parsed: dict) -> dict:
    """Reduce a parse result to labels. Does not keep the full genotype table."""
    genotypes = {str(k): str(v) for k, v in (parsed.get("genotypes") or {}).items()}
    highlights = []
    seen = []
    absent = []
    for entry in TRAITS:
        raw = genotypes.get(entry["rsid"])
        if raw is None or _alleles(raw) == "":
            absent.append(entry["rsid"])
            continue
        row = _public_row(entry, raw)
        wanted = {_alleles(item) for item in entry["when"]}
        if _alleles(raw) in wanted:
            highlights.append(row)
        else:
            seen.append(row)
    build = parsed.get("build")
    return {
        "marker_count": int(parsed.get("marker_count") or 0),
        "build": build,
        "build_label": {36: "NCBI36", 37: "GRCh37", 38: "GRCh38"}.get(build, "not detected"),
        "source": parsed.get("source") or "",
        "highlights": highlights,
        "seen": seen,
        "absent": absent,
        "educational": EDUCATIONAL,
    }
