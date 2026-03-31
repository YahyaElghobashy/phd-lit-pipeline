"""
Codegen — Generate extraction_prompt.py
=========================================
Generates a complete extraction_prompt.py from a ResearchConfig.

The generated file has the EXACT same structure as the hand-written original:
  - build_system_prompt() -> raw string with PhD context, schema, rubric, rules, dropdowns
  - build_user_prompt()   -> per-paper prompt (generic, identical for every config)
"""
from __future__ import annotations

import textwrap
from pathlib import Path

from codegen.config_loader import ResearchConfig, load_config


# ─── Helpers ──────────────────────────────────────────────


def _indent(text: str, n: int = 4) -> str:
    return textwrap.indent(text, " " * n)


def _papers_bullet_list(config: ResearchConfig) -> str:
    lines = []
    for p in config.papers:
        lines.append(f"- {p.label}: {p.focus}")
    return "\n".join(lines)


def _databases_line(config: ResearchConfig) -> str:
    parts = []
    for db in config.research_context.databases:
        parts.append(f"{db.name} ({db.purpose})")
    return "Available databases: " + " and ".join(parts) + "."


def _scholars_line(config: ResearchConfig) -> str:
    parts = []
    for s in config.key_scholars:
        parts.append(f"{s.name} ({s.context})")
    return "Key scholars: " + ", ".join(parts) + "."


def _theories_line(config: ResearchConfig) -> str:
    return "Theories: " + ", ".join(config.theories) + "."


def _custom_section_char_count(config: ResearchConfig) -> int:
    """Count the number of columns across all custom sections (for the task description)."""
    total = 0
    for sec in config.custom_sections:
        total += len(sec.columns)
    return total


# ─── Schema section builders ─────────────────────────────


def _section_6_theory(config: ResearchConfig) -> str:
    """Build the 6_THEORY JSON schema block with dynamic scholar columns."""
    lines = [
        '  "6_THEORY": {',
        '    "PAPER_ID": "",',
        '    "Primary_Theory": "", "Secondary_Theory_1": "", "Secondary_Theory_2": "",',
        '    "Theory_Application_Quality": "One of: Deep integration | Surface citation | Token mention | No theory",',
        '    "Theoretical_Predictions_Tested": "",',
        '    "Theoretical_Contribution": "One of: Extends theory | Confirms theory | Challenges theory | Combines theories | None",',
    ]
    for s in config.key_scholars:
        lines.append(f'    "Cites_{s.key}": "Yes | No", "{s.key}_Paper_Cited": "",')
    lines.append('    "Connection_To_Our_Theories": "How this paper\'s theoretical framework relates to ours"')
    lines.append("  },")
    return "\n".join(lines)


def _section_10_classification(config: ResearchConfig) -> str:
    """Build the 10_CLASSIFICATION JSON schema block with dynamic dropdowns."""
    primary_themes = config.dropdowns.get("Primary_Theme", [])
    theme_options = " | ".join(primary_themes) if primary_themes else "Other"

    paper_labels = [p.label for p in config.papers]
    extras = config.dropdowns.get("Paper_Assignment_extras", [])
    pa_options = " | ".join(paper_labels + extras) if paper_labels else "Other"

    lines = [
        '  "10_CLASSIFICATION": {',
        '    "PAPER_ID": "",',
        f'    "Primary_Theme": "MUST be exactly one of: {theme_options}",',
        '    "Secondary_Theme": "Same options as Primary_Theme, or empty",',
        f'    "Paper_Assignment": "MUST be exactly one of: {pa_options}",',
        '    "Use_Case_Theory": "Yes or No — does this paper inform our theoretical framework?",',
        '    "Use_Case_Methodology": "Yes or No — does this paper inform our methodology?",',
        '    "Use_Case_Variables": "Yes or No — does this paper inform our variable selection?",',
        '    "Use_Case_Measurement": "Yes or No — does this paper inform our measurement approach?",',
        '    "Use_Case_Context": "Yes or No — does this paper inform our contextual framing?",',
        '    "Use_Case_Gaps": "Yes or No — does this paper help identify our research gaps?",',
        '    "Use_Case_H_Support": "Yes or No — does this paper support any of our hypotheses?",',
        '    "Use_Case_H_Contradict": "Yes or No — does this paper contradict any of our hypotheses?",',
        '    "Gap_Cluster": "Short label (max 5 words) for the gap cluster this paper belongs to",',
        '    "Informs_Our_IV": "Yes or No",',
        '    "Informs_Our_DV": "Yes or No",',
        '    "Suggests_Moderators": "Yes or No",',
        '    "Suggests_Mediators": "Yes or No",',
        '    "Suggests_Controls": "Yes or No"',
        "  },",
    ]
    return "\n".join(lines)


def _section_11_connections(config: ResearchConfig) -> str:
    """Build the 11_CONNECTIONS JSON schema block with dynamic scholar columns."""
    lines = [
        '  "11_CONNECTIONS": {',
        '    "PAPER_ID": "",',
    ]
    for s in config.key_scholars:
        lines.append(f'    "Cites_{s.key}": "Yes | No", "{s.key}_Paper_Cited": "",')
    lines.append('    "Important_Refs_To_Add": "Key references we should also review",')
    lines.append('    "Related_Papers_In_DB": "Papers already in our database that relate",')
    lines.append('    "Builds_On": "", "Contradicts": "",')
    lines.append('    "Replication_Possible_With_Our_Data": "Yes | No | Partially",')
    lines.append('    "Replication_Notes": ""')
    lines.append("  },")
    return "\n".join(lines)


def _custom_sections_schema(config: ResearchConfig) -> str:
    """Build JSON schema blocks for custom sections (12+)."""
    blocks = []
    for sec in config.custom_sections:
        lines = [f'  "{sec.id}": {{', '    "PAPER_ID": "",']
        for i, col in enumerate(sec.columns):
            trailing = "," if i < len(sec.columns) - 1 else ""
            if col.type == "enum" and col.options:
                opts = " | ".join(col.options)
                lines.append(f'    "{col.name}": "{opts}"{trailing}')
            else:
                lines.append(f'    "{col.name}": ""{trailing}')
        lines.append("  },")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _custom_chars_count_text(config: ResearchConfig) -> str:
    """Build the task bullet for custom section characteristics."""
    parts = []
    for sec in config.custom_sections:
        col_count = len(sec.columns)
        parts.append(f"Map all {col_count} {sec.label.lower()} as examined/not examined")
    return parts[0] if parts else "Map custom characteristics as examined/not examined"


def _rubric_table(config: ResearchConfig) -> str:
    """Build the relevance rubric markdown table."""
    lines = [
        "| Dimension (Weight) | 1 | 3 | 5 |",
        "|---|---|---|---|",
    ]
    for d in config.relevance_rubric.dimensions:
        pct = int(d.weight * 100)
        lines.append(f"| {d.name.replace('_', ' ')} ({pct}%) | {d.scale_1} | {d.scale_3} | {d.scale_5} |")
    return "\n".join(lines)


def _rubric_formula(config: ResearchConfig) -> str:
    """Build the rubric formula string."""
    parts = []
    for d in config.relevance_rubric.dimensions:
        label = d.name.replace("_", " ")
        # Shorten label for formula
        short = label.split()[0] if " " in label else label
        parts.append(f"({short}\u00d7{d.weight:.2f})")
    return "Formula: " + " + ".join(parts)


def _dv_relevance_options(config: ResearchConfig) -> str:
    """Build DV_Relevance_To_Us dropdown options."""
    opts = []
    for p in config.papers:
        opts.append(f'"Direct match {p.label}"')
    extras = config.dropdowns.get("DV_Relevance_extras", [])
    for e in extras:
        opts.append(f'"{e}"')
    return " | ".join(opts)


def _paper_assignment_options(config: ResearchConfig) -> str:
    """Build Paper_Assignment dropdown options."""
    opts = []
    for p in config.papers:
        opts.append(f'"{p.label}"')
    extras = config.dropdowns.get("Paper_Assignment_extras", [])
    for e in extras:
        opts.append(f'"{e}"')
    return " | ".join(opts)


def _dropdown_lines(config: ResearchConfig) -> str:
    """Build the DROPDOWN / ENUMERATION FIELDS section."""
    lines = []
    # Static dropdowns
    lines.append('- Journal_Tier: "1-FT50/UTD24/ABS4*" | "2-ABS3-4/Good Field" | "3-ABS2/Decent" | "4-Other/Working Paper"')
    lines.append('- Paper_Type: "Empirical" | "Theoretical" | "Review" | "Meta-analysis" | "Qualitative" | "Mixed-methods" | "Bibliometric"')
    lines.append('- Aim_Type: "Causal" | "Associational" | "Descriptive" | "Exploratory" | "Confirmatory"')
    lines.append('- H*_Supported: "Yes" | "No" | "Partially" | "Not tested"')

    # DV_Category
    dv_cats = config.dropdowns.get("DV_Category", [])
    if dv_cats:
        opts = " | ".join(f'"{c}"' for c in dv_cats)
        lines.append(f"- DV*_Category: {opts}")

    # DV_Relevance_To_Us (dynamic from papers)
    lines.append(f"- DV*_Relevance_To_Us: {_dv_relevance_options(config)}")

    # IV_Type
    iv_types = config.dropdowns.get("IV_Type", [])
    if iv_types:
        opts = " | ".join(f'"{t}"' for t in iv_types)
        lines.append(f"- IV*_Type: {opts}")

    # IV_Role
    iv_roles = config.dropdowns.get("IV_Role", [])
    if iv_roles:
        opts = " | ".join(f'"{r}"' for r in iv_roles)
        lines.append(f"- IV*_Role_In_Our_Framework: {opts}")

    # Static methodology dropdowns
    lines.append('- Research_Design: "Cross-sectional" | "Panel-balanced" | "Panel-unbalanced" | "Event study" | "Quasi-experiment" | "DiD" | "RDD" | "Qualitative" | "Mixed" | "SLR/Bibliometric"')
    lines.append('- Estimation_Primary: "OLS" | "Fixed Effects" | "Random Effects" | "System GMM" | "Difference GMM" | "2SLS-IV" | "3SLS" | "Tobit" | "Logit" | "Probit" | "Heckman" | "PSM" | "DiD" | "Quantile Reg" | "SEM" | "Meta-regression" | "Other"')
    lines.append('- FE_Type: "Firm" | "Year" | "Industry" | "Country" | "Firm+Year" | "Firm+Year+Industry" | "None" | "Not stated"')
    lines.append('- RE_Used / Endogeneity_Acknowledged: "Yes" | "No" | "Not stated"')
    lines.append('- Methodology_Quality: "Strong" | "Adequate" | "Weak"')
    lines.append('- Geography_Type: "Single-country" | "Multi-country" | "Global"')
    lines.append('- Data_Overlap_With_Ours: "Full overlap" | "Partial overlap" | "No overlap" | "N/A"')
    lines.append('- Theory_Application_Quality: "Deep integration" | "Surface citation" | "Token mention" | "No theory"')
    lines.append('- Theoretical_Contribution: "Extends theory" | "Confirms theory" | "Challenges theory" | "Combines theories" | "None"')
    lines.append('- Effect_Direction: "Positive" | "Negative" | "Mixed" | "Null" | "Non-linear U" | "Non-linear inverted-U"')

    # Primary_Theme (dynamic)
    primary_themes = config.dropdowns.get("Primary_Theme", [])
    if primary_themes:
        opts = " | ".join(f'"{t}"' for t in primary_themes)
        lines.append(f"- Primary_Theme: {opts}")

    # Paper_Assignment (dynamic from papers)
    lines.append(f"- Paper_Assignment: {_paper_assignment_options(config)}")

    # Static Yes/No fields
    lines.append('- All Use_Case_* fields: "Yes" | "No"')
    lines.append('- Informs_Our_IV / Informs_Our_DV / Suggests_Moderators / Suggests_Mediators / Suggests_Controls: "Yes" | "No"')

    # Custom section enum fields
    for sec in config.custom_sections:
        enum_cols = [c for c in sec.columns if c.type == "enum"]
        if enum_cols:
            for col in enum_cols:
                opts = " | ".join(f'"{o}"' for o in col.options)
                lines.append(f'- {col.name}: {opts}')

    # Scholar citations
    for s in config.key_scholars:
        lines.append(f'- Cites_{s.key}: "Yes" | "No"')

    lines.append('- Replication_Possible_With_Our_Data: "Yes" | "No" | "Partially"')
    lines.append('- Data_Available (GAP_TRACKER): "Yes" | "No" | "Partially"')

    return "\n".join(lines)


# ─── Main generator ──────────────────────────────────────


def _build_system_prompt_string(config: ResearchConfig) -> str:
    """Build the raw system prompt string content."""
    papers_list = _papers_bullet_list(config)
    databases = _databases_line(config)
    scholars = _scholars_line(config)
    theories = _theories_line(config)
    critical_note = config.research_context.critical_note.strip()
    summary = config.research_context.summary.strip()
    custom_task_line = _custom_chars_count_text(config)

    # Number of papers for description
    n_papers = len(config.papers)
    paper_count_text = f"a {_number_word(n_papers)}-paper" if n_papers <= 10 else f"a {n_papers}-paper"

    # Section 6, 10, 11 dynamic
    sec6 = _section_6_theory(config)
    sec10 = _section_10_classification(config)
    sec11 = _section_11_connections(config)
    custom_secs = _custom_sections_schema(config)

    # Total sections count (static 1-5 + 7-9 = 8 static + section 6, 10, 11 = 3 dynamic + custom)
    total_sections = 11 + len(config.custom_sections)

    # Rubric
    rubric_table = _rubric_table(config)
    rubric_formula = _rubric_formula(config)

    # Dropdowns
    dropdowns = _dropdown_lines(config)

    # DV relevance options for section 3 schema
    dv_rel_options = []
    for p in config.papers:
        dv_rel_options.append(f"Direct match {p.label}")
    dv_rel_extras = config.dropdowns.get("DV_Relevance_extras", [])
    dv_rel_options.extend(dv_rel_extras)
    dv_rel_str = " | ".join(dv_rel_options)

    # Paper Assignment options for section 10 schema
    pa_options = []
    for p in config.papers:
        pa_options.append(p.label)
    pa_extras = config.dropdowns.get("Paper_Assignment_extras", [])
    pa_options.extend(pa_extras)
    pa_str = " | ".join(pa_options)

    # DV_Category options
    dv_cats = config.dropdowns.get("DV_Category", [])
    dv_cat_str = " | ".join(dv_cats) if dv_cats else "Financial Performance | ESG-Sustainability | Innovation-Patents | Digital-Technology | Risk | Other"

    # IV_Type options
    iv_types = config.dropdowns.get("IV_Type", [])
    iv_type_str = " | ".join(iv_types) if iv_types else "Gender diversity measure | Board characteristic | Firm characteristic | Other"

    # IV_Role options
    iv_roles = config.dropdowns.get("IV_Role", [])
    iv_role_str = " | ".join(iv_roles) if iv_roles else "Focal IV | Key moderator | Board control | Firm control | Not in our framework"

    prompt = f"""You are a scientific research extraction assistant for a PhD literature review.

# PHD RESEARCH CONTEXT

This pipeline serves {paper_count_text} PhD dissertation: "{config.project.title}."

{summary}
{papers_list}

CRITICAL: {critical_note}

{databases}

{scholars}

{theories}

# YOUR TASK

Read the provided PDF research paper and extract structured data into the exact JSON schema below. You are a SCIENTIFIC INTERPRETER, not a passive copier:
- Extract all fields per the schema
- Score relevance using the weighted rubric
- Classify the paper's theme and paper assignment
- {custom_task_line}
- Evaluate this paper against every existing gap in the tracker
- Identify new gaps this paper reveals
- Provide a narrative assessment

# OUTPUT FORMAT

Return ONLY a valid JSON object matching the schema below. No markdown wrapping, no explanation text outside the JSON. Every field must be present (use empty string "" for unavailable text fields, 0 for unavailable numeric fields, "N/A" for not-applicable fields).

# EXTRACTION SCHEMA

{{
  "paper_id": "FirstAuthor_Year_Keyword (e.g., Adams_2009_Women)",

  "Verbatim_Abstract": "The paper's abstract copied EXACTLY word-for-word from the PDF. Do not paraphrase or summarize. If no abstract section exists, use empty string.",

  "1_IDENTIFICATION": {{
    "PAPER_ID": "same as paper_id",
    "Full_Citation_APA7": "Full APA 7th edition citation",
    "DOI": "DOI if available, else empty string",
    "Authors": "All authors comma-separated",
    "Year": 2024,
    "Journal": "Journal name",
    "Journal_Tier": "One of: 1-FT50/UTD24/ABS4* | 2-ABS3-4/Good Field | 3-ABS2/Decent | 4-Other/Working Paper",
    "Paper_Type": "One of: Empirical | Theoretical | Review | Meta-analysis | Qualitative | Mixed-methods | Bibliometric",
    "Citation_Count": "If stated, else empty",
    "Search_Query_Source": "How this paper was found, if known",
    "Date_Extracted": "FILLED BY PIPELINE",
    "Extracted_By": "Claude Code Pipeline"
  }},

  "2_RESEARCH_DESIGN": {{
    "PAPER_ID": "",
    "Research_Question": "Primary RQ verbatim or paraphrased",
    "Secondary_Questions": "Additional RQs if any",
    "Aim_Type": "One of: Causal | Associational | Descriptive | Exploratory | Confirmatory",
    "H1_Statement": "", "H1_Direction": "", "H1_Supported": "Yes | No | Partially | Not tested",
    "H2_Statement": "", "H2_Direction": "", "H2_Supported": "",
    "H3_Statement": "", "H3_Direction": "", "H3_Supported": "",
    "H4_Statement": "", "H4_Direction": "", "H4_Supported": "",
    "Additional_Hypotheses": "Any hypotheses beyond H4",
    "One_Sentence_Summary": "One sentence capturing the paper's core contribution"
  }},

  "3_VARIABLES": {{
    "PAPER_ID": "",
    "DV1_Name": "", "DV1_Measurement": "How measured (formula/proxy/index)",
    "DV1_Source": "Data source (e.g., database name, hand-collected)",
    "DV1_Category": "One of: {dv_cat_str}",
    "DV1_Relevance_To_Us": "One of: {dv_rel_str}",
    "DV2_Name": "", "DV2_Measurement": "", "DV2_Source": "", "DV2_Category": "",
    "IV1_Name": "", "IV1_Measurement": "",
    "IV1_Type": "One of: {iv_type_str}",
    "IV1_Detail": "Detailed description of how this IV is operationalized",
    "IV1_Role_In_Our_Framework": "One of: {iv_role_str}",
    "IV2_Name": "", "IV2_Measurement": "", "IV2_Type": "", "IV2_Detail": "",
    "IV3_Name": "", "IV3_Measurement": "", "IV3_Type": "", "IV3_Detail": "",
    "Moderator1_Name": "", "Moderator1_Measurement": "", "Moderator1_Interaction": "", "Moderator1_Finding": "",
    "Moderator2_Name": "", "Moderator2_Measurement": "", "Moderator2_Interaction": "", "Moderator2_Finding": "",
    "Mediator1_Name": "", "Mediator1_Measurement": "", "Mediator1_Pathway": "", "Mediator1_Confirmed": "",
    "Mediator2_Name": "", "Mediator2_Measurement": "", "Mediator2_Pathway": "", "Mediator2_Confirmed": "",
    "Controls_List": "Comma-separated list of all control variables",
    "Controls_Count": 0,
    "Instrument1_Name": "", "Instrument1_Measurement": "", "Instrument1_Validity": ""
  }},

  "4_METHODOLOGY": {{
    "PAPER_ID": "",
    "Research_Design": "One of: Cross-sectional | Panel-balanced | Panel-unbalanced | Event study | Quasi-experiment | DiD | RDD | Qualitative | Mixed | SLR/Bibliometric",
    "Estimation_Primary": "One of: OLS | Fixed Effects | Random Effects | System GMM | Difference GMM | 2SLS-IV | 3SLS | Tobit | Logit | Probit | Heckman | PSM | DiD | Quantile Reg | SEM | Meta-regression | Other",
    "Estimation_Secondary": "",
    "FE_Type": "One of: Firm | Year | Industry | Country | Firm+Year | Firm+Year+Industry | None | Not stated",
    "RE_Used": "One of: Yes | No | Not stated",
    "Hausman_Result": "",
    "Clustering_Level": "",
    "Endogeneity_Acknowledged": "One of: Yes | No | Not stated",
    "Endogeneity_Methods": "",
    "Instruments_Used": "",
    "Instrument_Validity_Tests": "",
    "Reverse_Causality_Addressed": "",
    "Omitted_Var_Addressed": "",
    "Robustness_Check_1": "", "Robustness_Check_2": "", "Robustness_Check_3": "", "Robustness_Check_4": "",
    "Econometric_Equation": "The main regression equation if stated",
    "Software_Used": "",
    "Methodology_Quality": "One of: Strong | Adequate | Weak",
    "Quality_Justification": "Why you rated the methodology this way"
  }},

  "5_SAMPLE": {{
    "PAPER_ID": "",
    "Countries": "", "Geography_Type": "Single-country | Multi-country | Global",
    "N_Firms": "", "N_Observations": "",
    "Period_Start": "", "Period_End": "",
    "Industries_Included": "", "Industries_Excluded": "",
    "Listing_Requirement": "",
    "Data_Sources": "",
    "Data_Overlap_With_Ours": "One of: Full overlap | Partial overlap | No overlap | N/A",
    "Sample_Selection_Notes": "",
    "Survivorship_Bias_Addressed": ""
  }},

{sec6}

  "7_FINDINGS": {{
    "PAPER_ID": "",
    "Main_Finding": "",
    "Effect_Direction": "One of: Positive | Negative | Mixed | Null | Non-linear U | Non-linear inverted-U",
    "Coefficient_Beta": "", "Standard_Error": "", "P_Value": "",
    "Economic_Significance": "",
    "Moderating_Effects_Found": "", "Mediating_Effects_Found": "",
    "Heterogeneity_Results": "",
    "Contradictions_With_Literature": "",
    "Mechanisms_Channels_Identified": ""
  }},

  "8_GAPS_LIMITATIONS": {{
    "PAPER_ID": "",
    "Stated_Limitation_1": "", "Stated_Limitation_2": "", "Stated_Limitation_3": "",
    "Future_Research_1": "", "Future_Research_2": "", "Future_Research_3": "",
    "OUR_Theoretical_Gap": "Gap WE identify from a theoretical perspective",
    "OUR_Methodological_Gap": "Gap WE identify from a methodological perspective",
    "OUR_Variable_Gap": "Gap WE identify regarding variables/measurements",
    "OUR_Contextual_Gap": "Gap WE identify regarding context/sample",
    "OUR_Mechanism_Gap": "Gap WE identify regarding mechanisms/pathways",
    "What_To_Adopt": "What we should borrow from this paper",
    "What_To_Avoid": "What weaknesses we should NOT replicate",
    "Our_Critical_Assessment": "Our overall assessment of this paper's strengths and weaknesses"
  }},

  "9_RELEVANCE": {{
    "PAPER_ID": "",
    "Topic_Alignment": "1-5 integer",
    "Variable_Usefulness": "1-5 integer",
    "Methodological_Value": "1-5 integer",
    "Theoretical_Contribution": "1-5 integer",
    "Recency": "1-5 integer",
    "Publication_Quality": "1-5 integer",
    "Weighted_Score": "DO NOT COMPUTE \u2014 leave as empty string. The Google Sheet calculates this via formula.",
    "Relevance_Tier": "DO NOT COMPUTE \u2014 leave as empty string. The Google Sheet calculates this via formula.",
    "Scoring_Justification": "1-2 sentences max explaining the scores"
  }},

{sec10}

{sec11}

{custom_secs}

  "gap_analysis": {{
    "existing_gaps_updated": [
      {{
        "gap_id": "GAP_XXX",
        "new_coverage_level": "One of: DIRECTLY TACKLED | SUBSTANTIALLY COVERED | PARTIALLY ADDRESSED | NOT ADDRESSED",
        "covering_paper_id": "this paper's ID",
        "coverage_notes": "Why this coverage level"
      }}
    ],
    "new_gaps_identified": [
      {{
        "gap_id": "GAP_NEW_XXX",
        "gap_type": "One of: Theoretical | Methodological | Variable | Contextual | Mechanism",
        "gap_statement": "Clear statement of what is missing in the literature",
        "severity": 4,
        "feasibility": 5,
        "novelty": 5,
        "paper_assignment": "Which of our {n_papers} papers this gap belongs to",
        "potential_hypothesis": "",
        "variables_needed": "",
        "methodology_needed": "",
        "data_available": "Yes | No | Partially",
        "coverage_level": "NOT ADDRESSED",
        "status": "Identified"
      }}
    ]
  }},

  "narrative_assessment": "100-word assessment of this paper's contribution to our PhD project"
}}

# RELEVANCE SCORING RUBRIC

Score each dimension 1-5:

{rubric_table}

{rubric_formula}

Tiers: Essential \u2265 4.5 | Highly Relevant 3.5\u20134.4 | Moderate 2.5\u20133.4 | Low < 2.5

# GAP COVERAGE LEVELS

| Level | Definition |
|---|---|
| DIRECTLY TACKLED | Paper's RQ explicitly addresses this gap. Gap is closed. |
| SUBSTANTIALLY COVERED | Paper provides strong evidence but doesn't target the gap directly. |
| PARTIALLY ADDRESSED | Paper touches the gap tangentially. Gap remains open. |
| NOT ADDRESSED | Paper has no bearing on this gap. |

# IMPORTANT RULES

1. Every field must be present in the output JSON. Use "" for unavailable text, 0 for unavailable numbers, "N/A" for not-applicable.
2. PAPER_ID must be consistent across ALL sections.
3. Relevance scores must be integers 1-5. Weighted_Score and Relevance_Tier: leave as empty string "" \u2014 the Google Sheet calculates these via formula.
4. For gap_analysis.existing_gaps_updated: evaluate EVERY gap provided in the gap context. If the paper doesn't address a gap, set coverage to "NOT ADDRESSED".
5. For new gaps: only identify gaps that are genuinely new and not already in the tracker.
6. Be a critical scientific interpreter. Don't just copy abstracts \u2014 analyze methodology, assess quality, identify what the paper means for OUR specific research.
7. Remember: our DVs are NON-MONETARY ({critical_note.split('.')[0] if '.' in critical_note else critical_note}). Papers using only financial DVs are relevant as methodology/control references, not as direct matches.
8. Verbatim_Abstract must be the exact text from the paper's "Abstract" section, copied word-for-word. Do not paraphrase, summarize, or interpret. If the paper has no abstract, use empty string "".

# CRITICAL \u2014 DROPDOWN / ENUMERATION FIELDS

The Google Sheet has data validation dropdowns. You MUST use EXACTLY one of the listed options for these fields \u2014 no paraphrasing, no custom text:

{dropdowns}

If the paper's method doesn't exactly match an option, pick the CLOSEST match. Never invent new option values."""

    return prompt


def _number_word(n: int) -> str:
    """Convert small integers to words."""
    words = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
             6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten"}
    return words.get(n, str(n))


# ─── File generation ──────────────────────────────────────


def generate(config: ResearchConfig, output_path: str = "extraction_prompt.py") -> None:
    """
    Generate a complete extraction_prompt.py from a ResearchConfig.

    The generated file contains:
      - build_system_prompt() -> str
      - build_user_prompt(pdf_path, gap_state, paper_index, total_papers) -> str
    """
    system_prompt_content = _build_system_prompt_string(config)

    # Escape backslashes and triple-quotes for embedding in a raw string
    # The prompt itself should not contain ''' so we're safe with triple-quote delimiters
    # We use a regular string (not raw) and escape accordingly
    # Actually, let's use a function that returns the string built at import time.

    file_content = '''"""
PhD Literature Extraction Pipeline \u2014 Prompt Templates
======================================================
Builds the system prompt and per-paper user prompt for Claude CLI.

AUTO-GENERATED by codegen/generate_extraction_prompt.py
Do not edit manually \u2014 re-run the generator instead.
"""
from __future__ import annotations

import json


def build_system_prompt() -> str:
    """
    Static system prompt with PhD context, extraction schema, and scoring rubric.
    Sent via --append-system-prompt to Claude CLI (constant across all papers).
    """
    return r"""''' + system_prompt_content + '''"""


def build_user_prompt(
    pdf_path: str,
    gap_state: list[dict],
    paper_index: int,
    total_papers: int,
) -> str:
    """
    Per-paper user prompt with PDF path and gap context.
    """
    # Compact gap state (only unresolved, essential fields)
    compact_gaps = []
    for g in gap_state:
        compact_gaps.append({
            "gap_id": g.get("gap_id", ""),
            "statement": g.get("gap_statement", g.get("statement", "")),
            "type": g.get("gap_type", g.get("type", "")),
            "coverage": g.get("coverage_level", "NOT ADDRESSED"),
            "paper_assignment": g.get("paper_assignment", ""),
        })

    gap_context = json.dumps(compact_gaps, indent=None) if compact_gaps else "[]"

    prompt = f"""Read the research paper PDF at this path and extract all data following the schema in your instructions.

PDF PATH: {pdf_path}

PAPER {paper_index} OF {total_papers}

INSTRUCTIONS:
1. Use the Read tool to read the PDF file at the path above. If it's longer than 20 pages, read it in chunks (pages 1-20, then 21-40, etc.).
2. Extract ALL fields per the schema in your system prompt.
3. Determine the paper's theme and classification entirely from its content \u2014 do NOT rely on folder names or file names.
4. Evaluate this paper against every existing gap listed below.
5. Identify any NEW gaps this paper reveals.
6. Return ONLY a valid JSON object. No markdown, no explanation outside the JSON.

EXISTING GAPS TO EVALUATE AGAINST:
{gap_context}

Remember: Return pure JSON only."""

    return prompt
'''

    output = Path(output_path)
    output.write_text(file_content, encoding="utf-8")
    print(f"Generated {output.resolve()}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate extraction_prompt.py from research config")
    parser.add_argument("--config", default="research_config.yaml", help="Path to research_config.yaml")
    parser.add_argument("--output", default="extraction_prompt.py", help="Output path")
    args = parser.parse_args()

    cfg = load_config(args.config)
    generate(cfg, args.output)
