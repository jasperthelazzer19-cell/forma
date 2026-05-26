"""
Compile the official ACT tests inventory from web research (May 2026).

Source data is from:
  - quantumactprep.com/act-official-tests   → master list of 56 released forms 2005-2023
  - quantumactprep.com/actpracticetests    → 9 "unique" tests recycled as official prep
  - act.org                                 → 3 free PDFs (Preparing-for-the-ACT etc.)
  - mcelroytutoring.com                     → ~106 form list, most PDFs taken down
  - piqosity.com                            → 3 Google Drive PDFs of recycled tests
  - mysatactprep.com / schs.cards           → archived PDFs

Outputs (in this dir):
  - web_official_act_inventory.csv
  - web_official_act_inventory.json
  - web_official_act_inventory.md
"""
import csv
import json
import os
from collections import defaultdict

HERE = "/Users/jasperlasser/actprep-crackab"

# ── Master list of released ACT forms (Quantum 2005-2023) ──────────
# Each entry: (form_code, year, month, source_url, pdf_url_if_known)
QUANTUM_RELEASED = [
    ("G01",   2023, "September", "https://quantumactprep.com/act-official-tests/video-explanations-2023-september-act-g01", None),
    ("F12",   2023, "June",      "https://quantumactprep.com/act-official-tests/video-explanations-2023-june-act-f12",      None),
    ("F11",   2023, "April",     "https://quantumactprep.com/act-official-tests/video-explanations-2023-april-act-f11",     None),
    ("Z18",   2023, "April",     "https://quantumactprep.com/act-official-tests/video-explanations-2023-april-act-z18",     None),
    ("F07",   2022, "December",  "https://quantumactprep.com/act-official-tests/video-explanations-2022-december-act-f07",  None),
    ("E26",   2022, "June",      "https://quantumactprep.com/act-official-tests/video-explanations-2022-june-act-e26",      None),
    ("E25",   2022, "April",     "https://quantumactprep.com/act-official-tests/video-explanations-2022-april-act-e25",     None),
    ("Z08",   2022, "April",     "https://quantumactprep.com/act-official-tests/video-explanations-2022-april-act-z08",     None),
    ("E23",   2021, "December",  "https://quantumactprep.com/act-official-tests/video-explanations-2021-december-act-e23",  None),
    ("D06",   2021, "June",      "https://quantumactprep.com/act-official-tests/video-explanations-2021-june-act-d06",      None),
    ("D05",   2021, "April",     "https://quantumactprep.com/act-official-tests/video-explanations-2021-april-act-d05",     None),
    ("Z04",   2021, "April",     "https://quantumactprep.com/act-official-tests/video-explanations-2021-april-act-z04",     None),
    ("D03",   2020, "December",  "https://quantumactprep.com/act-official-tests/video-explanations-2020-december-act-d03",  None),
    ("C01",   2020, "July",      "https://quantumactprep.com/act-official-tests/video-explanations-2020-july-act-c01",      None),
    ("C02",   2020, "June",      "https://quantumactprep.com/act-official-tests/video-explanations-2020-june-act-c02",      None),
    ("C03",   2019, "December",  "https://quantumactprep.com/act-official-tests/video-explanations-2019-december-act-c03",  None),
    ("B02",   2019, "June",      "https://quantumactprep.com/act-official-tests/2019-june-act-b02",                         None),
    ("B04",   2019, "April",     "https://quantumactprep.com/act-official-tests/2019-april-act-b04",                        None),
    ("Z15",   2019, "April",     "https://quantumactprep.com/act-official-tests/2019-april-act-z15",                        None),
    ("B05",   2018, "December",  "https://quantumactprep.com/act-official-tests/2018-act-december-b05",                     None),
    ("A11",   2018, "June",      "https://quantumactprep.com/act-official-tests/2018-june-act-a11",                         None),
    ("A09",   2018, "April",     "https://quantumactprep.com/act-official-tests/2018-act-april-a09",                        None),
    ("A10",   2017, "December",  "https://quantumactprep.com/act-official-tests/2017-act-december-a10",                     None),
    ("74C",   2017, "June",      "https://quantumactprep.com/act-official-tests/2017-june-act74c",                          None),
    ("74F",   2017, "April",     "https://quantumactprep.com/act-official-tests/2017-april-act74f",                         "https://mysatactprep.com/wp-content/uploads/2019/11/ACTPracticeTest2018-2019.pdf"),
    ("74H",   2016, "December",  "https://quantumactprep.com/act-official-tests/2016-act-december-74h",                     None),
    ("72F",   2016, "June",      "https://quantumactprep.com/act-official-tests/2016-june-act72f",                          None),
    ("73E",   2016, "April",     "https://quantumactprep.com/act-official-tests/2016-april-act-73e",                        None),
    ("72E",   2015, "December",  "https://quantumactprep.com/act-official-tests/2015-december-act72e",                      None),
    ("73C",   2015, "June",      "https://quantumactprep.com/act-official-tests/2015-june-act-73c",                         None),
    ("73G",   2015, "April",     "https://quantumactprep.com/act-official-tests/2015-april-act-73g",                        None),
    ("72G",   2014, "December",  "https://quantumactprep.com/act-official-tests/2014-dec-act",                              None),
    ("72C",   2014, "June",      "https://quantumactprep.com/act-official-tests/2014-act-june-72c",                         "https://drive.google.com/file/d/1hBc2wdW_ZUChsDu_YO7lYym4verktG02/view"),
    ("71H",   2014, "April",     "https://quantumactprep.com/act-official-tests/2014-act-april-71h",                        None),
    ("71E",   2013, "December",  "https://quantumactprep.com/act-official-tests/2013-act-december-71e",                     None),
    ("71C",   2013, "June",      "https://quantumactprep.com/act-official-tests/2013-act-june-71c",                         None),
    ("71G",   2013, "April",     "https://quantumactprep.com/act-official-tests/2013-act-april-71g",                        None),
    ("71A",   2012, "December",  "https://quantumactprep.com/act-official-tests/2012-act-december-71a",                     None),
    ("70C",   2012, "June",      "https://quantumactprep.com/act-official-tests/2012-act-june-70c",                         None),
    ("70G",   2012, "April",     "https://quantumactprep.com/act-official-tests/2012-act-april-70g",                        None),
    ("70A",   2011, "December",  "https://quantumactprep.com/act-official-tests/2011-act-december-70a",                     None),
    ("69F",   2011, "June",      "https://quantumactprep.com/act-official-tests/2011-act-june-69f",                         None),
    ("67F",   2011, "April",     "https://quantumactprep.com/act-official-tests/2011-act-april-67f",                        None),
    ("69A",   2010, "December",  "https://quantumactprep.com/act-official-tests/2010-act-december-69a",                     None),
    ("68C",   2010, "June",      "https://quantumactprep.com/act-official-tests/2010-act-june-68c",                         None),
    ("68G",   2010, "April",     "https://quantumactprep.com/act-official-tests/2010-act-april-68g",                        None),
    ("68A",   2009, "December",  "https://quantumactprep.com/act-official-tests/2009-act-dec-68a",                          None),
    ("67C",   2009, "June",      "https://quantumactprep.com/act-official-tests/2009-act-june-67c",                         None),
    ("66F",   2009, "April",     "https://quantumactprep.com/act-official-tests/2009-act-april-66f",                        None),
    ("67A",   2008, "December",  "https://quantumactprep.com/act-official-tests/2008-act-december-67a",                     None),
    ("66C",   2008, "June",      "https://quantumactprep.com/act-official-tests/2008-act-june-66c",                         None),
    ("65D",   2008, "April",     "https://quantumactprep.com/act-official-tests/2008-act-april-65d",                        None),
    ("65E",   2007, "December",  "https://quantumactprep.com/act-official-tests/2007-act-dec-65e",                          None),
    ("65C",   2007, "June",      "https://quantumactprep.com/act-official-tests/2007-act-june-65c",                         None),
    ("64E",   2007, "April",     "https://quantumactprep.com/act-official-tests/2007-act-april-64e",                        "https://www.schs.cards/wp-content/uploads/2023/03/Test_1.pdf"),
    ("63D",   2006, "December",  "https://quantumactprep.com/act-official-tests/2006-act-dec-63d-test",                     None),
    ("63F",   2006, "June",      "https://quantumactprep.com/act-official-tests/2006-act-june-63f-test",                    None),
    ("63E",   2006, "April",     "https://quantumactprep.com/act-official-tests/2006-act-april-63e-test",                   None),
    ("61C",   2006, "January",   None,                                                                                       "https://www.schs.cards/wp-content/uploads/2023/03/Test_2.pdf"),
    ("63C",   2005, "December",  "https://quantumactprep.com/act-official-tests/2005-act-dec-63c-test",                     None),
    ("60E",   2005, "April",     "https://quantumactprep.com/act-official-tests/2005-act-april-60e-test",                   None),
]

# ── "Preparing for the ACT" booklets (recycled tests, year-stamped) ─
PREPARING_FOR_THE_ACT = [
    ("25MC1",    2025, "Annual", "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT.pdf",        "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT.pdf"),
    ("25MC5",    2025, "Annual", "https://www.act.org/content/dam/act/secured/documents/ACT-Test-Prep-ACT-Practice-Test-2-Form.pdf", "https://www.act.org/content/dam/act/secured/documents/ACT-Test-Prep-ACT-Practice-Test-2-Form.pdf"),
    ("2176CPRE", 2024, "Annual", "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT-24-25.pdf",  "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT-24-25.pdf"),
    ("2176CPRE-DRIVE", 2024, "Annual", "https://piqosity.com",                                                               "https://drive.google.com/file/d/1x7dZRGm7M3txlByS04XlQ-rQ4R8_FepL/view"),
    ("74FPRE",   2020, "Annual", "https://piqosity.com",                                                                     "https://drive.google.com/file/d/1oYlQ-xf32BQLsyVS5G4iuuxx2GZLoMXN/view"),
    ("72CPRE",   2017, "Annual", "https://piqosity.com",                                                                     "https://drive.google.com/file/d/1hBc2wdW_ZUChsDu_YO7lYym4verktG02/view"),
    ("PFTA-ES",  2025, "Annual", "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT-Spanish.pdf", "https://www.act.org/content/dam/act/unsecured/documents/Preparing-for-the-ACT-Spanish.pdf"),
]

# ── Known duplicate / recycle relationships ────────────────────────
# Piqosity confirms: Preparing-for-the-ACT booklets are actual released forms
# rebranded by year. Known mappings:
#   72CPRE = Form 72C (June 2014)
#   74FPRE = Form 74F (April 2017)
#   2176CPRE = released test from 2021 era
RECYCLE_MAP = {
    "72CPRE": "72C",
    "74FPRE": "74F",
}


def build_records():
    records = []
    for code, yr, mo, src, pdf in QUANTUM_RELEASED:
        records.append({
            "form_code": code,
            "year": yr,
            "month": mo,
            "source_url": src,
            "pdf_url": pdf,
            "sections": {
                "English": True, "Math": True, "Reading": True,
                "Science": True, "Writing": False,
            },
            "has_answer_key": True,        # released forms always include keys
            "has_explanations": True,      # via Quantum video playlists
            "appears_official": True,
            "appears_third_party": False,
            "confidence": 0.95 if pdf else 0.75,  # higher when we have direct PDF
            "duplicate_of": None,
            "notes": "ACT released TIR form; Quantum has video walkthroughs",
            "type": "released_form",
        })
    for code, yr, mo, src, pdf in PREPARING_FOR_THE_ACT:
        is_dup = code in RECYCLE_MAP
        records.append({
            "form_code": code,
            "year": yr,
            "month": mo,
            "source_url": src,
            "pdf_url": pdf,
            "sections": {
                "English": True, "Math": True, "Reading": True,
                "Science": True, "Writing": True,  # PFTA booklet includes writing prompt
            },
            "has_answer_key": True,
            "has_explanations": True,
            "appears_official": True,
            "appears_third_party": False,
            "confidence": 0.99,   # official act.org / verified recycle
            "duplicate_of": RECYCLE_MAP.get(code),
            "notes": "Preparing for the ACT booklet (free official); year-stamped",
            "type": "preparing_for_the_act",
        })
    return records


def emit(records):
    csv_p = os.path.join(HERE, "web_official_act_inventory.csv")
    json_p = os.path.join(HERE, "web_official_act_inventory.json")
    md_p = os.path.join(HERE, "web_official_act_inventory.md")

    with open(csv_p, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "form_code", "year", "month", "type",
            "source_url", "pdf_url",
            "english", "math", "reading", "science", "writing",
            "has_answer_key", "has_explanations",
            "appears_official", "confidence", "duplicate_of", "notes",
        ])
        for r in records:
            w.writerow([
                r["form_code"], r["year"], r["month"], r["type"],
                r["source_url"] or "", r["pdf_url"] or "",
                r["sections"]["English"], r["sections"]["Math"],
                r["sections"]["Reading"], r["sections"]["Science"],
                r["sections"]["Writing"],
                r["has_answer_key"], r["has_explanations"],
                r["appears_official"], r["confidence"],
                r["duplicate_of"] or "", r["notes"],
            ])

    with open(json_p, "w") as f:
        json.dump(records, f, indent=2)

    # Markdown
    n_total = len(records)
    n_unique = sum(1 for r in records if not r["duplicate_of"])
    n_with_pdf = sum(1 for r in records if r["pdf_url"])
    n_released = sum(1 for r in records if r["type"] == "released_form")
    n_prep = sum(1 for r in records if r["type"] == "preparing_for_the_act")

    by_year = defaultdict(list)
    for r in records:
        if r["type"] == "released_form":
            by_year[r["year"]].append(r)
    direct_pdfs = sorted(
        [r for r in records if r["pdf_url"]],
        key=lambda r: (-r["confidence"], r["year"] or 0, r["form_code"]),
    )

    with open(md_p, "w") as f:
        f.write("# Official ACT Tests — Web Inventory\n\n")
        f.write("_Compiled May 2026 from quantumactprep, mcelroytutoring, act.org, piqosity._\n\n")
        f.write("## Headline numbers\n\n")
        f.write(f"- **Total entries:** {n_total}\n")
        f.write(f"- **Unique (non-duplicate):** {n_unique}\n")
        f.write(f"- **Released TIR forms (2005-2023):** {n_released}\n")
        f.write(f"- **Preparing for the ACT booklets:** {n_prep}\n")
        f.write(f"- **Entries with direct PDF URL:** {n_with_pdf}\n\n")
        f.write("## Key insight\n\n")
        f.write("Per McElroy Tutoring + Quantum: ACT has only ~9 *truly unique* tests in active circulation. ")
        f.write("The Preparing-for-the-ACT booklets recycle past released forms (e.g. 72CPRE = Form 72C, ")
        f.write("74FPRE = Form 74F). Most direct PDF links to TIR exams were taken down after a 2022-ish ")
        f.write("legal notice from ACT to McElroy. Form codes still let you Google-find most PDFs.\n\n")

        f.write("## Best PDFs to scrape first (have direct download URLs)\n\n")
        f.write("| Form | Year | Month | Source | PDF |\n")
        f.write("| --- | --- | --- | --- | --- |\n")
        for r in direct_pdfs:
            src_host = (r["source_url"] or "").split("/")[2] if r["source_url"] else "—"
            f.write(f"| {r['form_code']} | {r['year']} | {r['month']} | {src_host} | "
                    f"[pdf]({r['pdf_url']}) |\n")

        f.write("\n## All released TIR forms by year\n\n")
        for yr in sorted(by_year.keys(), reverse=True):
            f.write(f"### {yr}\n\n")
            for r in by_year[yr]:
                pdf_str = f" [pdf]({r['pdf_url']})" if r["pdf_url"] else ""
                f.write(f"- **{r['form_code']}** ({r['month']}) — "
                        f"[Quantum walkthrough]({r['source_url']}){pdf_str}\n")
            f.write("\n")

        f.write("## Preparing for the ACT booklets (free official, recycled forms)\n\n")
        for r in [x for x in records if x["type"] == "preparing_for_the_act"]:
            dup_note = f" — recycle of **{r['duplicate_of']}**" if r["duplicate_of"] else ""
            f.write(f"- **{r['form_code']}** ({r['year']}){dup_note} — "
                    f"[pdf]({r['pdf_url']})\n")

        f.write("\n## Gaps / what's missing\n\n")
        missing_pdfs = [r for r in records if r["type"] == "released_form" and not r["pdf_url"]]
        f.write(f"- **{len(missing_pdfs)} released forms have no direct PDF in this inventory.** ")
        f.write("McElroy removed them after ACT legal notice. To find them: Google the form code "
                "(e.g. `\"Form 72E\" filetype:pdf`) — often surfaces on tutor sites, Reddit, ")
        f.write("Discord exports, or school district sites.\n")
        f.write("- **Form codes I could not verify against multiple sources:** Z04, Z08, Z15, Z18 ")
        f.write("(Quantum lists these as April supplemental forms; may overlap with main April forms ")
        f.write("of those years).\n")

        f.write("\n## Sources used\n\n")
        f.write("- [quantumactprep.com/act-official-tests](https://quantumactprep.com/act-official-tests)\n")
        f.write("- [mcelroytutoring.com 106-list](https://mcelroytutoring.com/lower.php?url=44-official-sat-pdfs-and-82-official-act-pdf-practice-tests-free)\n")
        f.write("- [piqosity.com free ACT PDFs](https://www.piqosity.com/free-act-official-practice-test-pdfs-and-answer-explanations)\n")
        f.write("- [act.org free test prep](https://www.act.org/content/act/en/products-and-services/the-act/test-preparation/free-act-test-prep.html)\n")

    return csv_p, json_p, md_p


if __name__ == "__main__":
    records = build_records()
    c, j, m = emit(records)
    print(f"wrote {c}")
    print(f"wrote {j}")
    print(f"wrote {m}")
    print(f"\n{len(records)} total entries, {sum(1 for r in records if r['pdf_url'])} with direct PDFs")
