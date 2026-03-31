"""
Codegen — Generate schemas.py
===============================
Generates schemas.py from a ResearchConfig.

The generated file contains:
  - COLUMNS dict with all section column orders
  - EXTRACTION_SECTIONS list
  - validate_extraction() function
"""
from __future__ import annotations

from pathlib import Path

from codegen.config_loader import ResearchConfig, load_config


# ─── Static sections (identical regardless of config) ────


STATIC_COLUMNS = {
    "1_IDENTIFICATION": [
        "PAPER_ID", "Full_Citation_APA7", "DOI", "Authors", "Year",
        "Journal", "Journal_Tier", "Paper_Type", "Citation_Count",
        "Search_Query_Source", "Date_Extracted", "Extracted_By",
    ],
    "2_RESEARCH_DESIGN": [
        "PAPER_ID", "Research_Question", "Secondary_Questions", "Aim_Type",
        "H1_Statement", "H1_Direction", "H1_Supported",
        "H2_Statement", "H2_Direction", "H2_Supported",
        "H3_Statement", "H3_Direction", "H3_Supported",
        "H4_Statement", "H4_Direction", "H4_Supported",
        "Additional_Hypotheses", "One_Sentence_Summary",
    ],
    "3_VARIABLES": [
        "PAPER_ID",
        "DV1_Name", "DV1_Measurement", "DV1_Source", "DV1_Category", "DV1_Relevance_To_Us",
        "DV2_Name", "DV2_Measurement", "DV2_Source", "DV2_Category",
        "IV1_Name", "IV1_Measurement", "IV1_Type", "IV1_Detail", "IV1_Role_In_Our_Framework",
        "IV2_Name", "IV2_Measurement", "IV2_Type", "IV2_Detail",
        "IV3_Name", "IV3_Measurement", "IV3_Type", "IV3_Detail",
        "Moderator1_Name", "Moderator1_Measurement", "Moderator1_Interaction", "Moderator1_Finding",
        "Moderator2_Name", "Moderator2_Measurement", "Moderator2_Interaction", "Moderator2_Finding",
        "Mediator1_Name", "Mediator1_Measurement", "Mediator1_Pathway", "Mediator1_Confirmed",
        "Mediator2_Name", "Mediator2_Measurement", "Mediator2_Pathway", "Mediator2_Confirmed",
        "Controls_List", "Controls_Count",
        "Instrument1_Name", "Instrument1_Measurement", "Instrument1_Validity",
    ],
    "4_METHODOLOGY": [
        "PAPER_ID", "Research_Design", "Estimation_Primary", "Estimation_Secondary",
        "FE_Type", "RE_Used", "Hausman_Result", "Clustering_Level",
        "Endogeneity_Acknowledged", "Endogeneity_Methods", "Instruments_Used",
        "Instrument_Validity_Tests", "Reverse_Causality_Addressed", "Omitted_Var_Addressed",
        "Robustness_Check_1", "Robustness_Check_2", "Robustness_Check_3", "Robustness_Check_4",
        "Econometric_Equation", "Software_Used",
        "Methodology_Quality", "Quality_Justification",
    ],
    "5_SAMPLE": [
        "PAPER_ID", "Countries", "Geography_Type", "N_Firms", "N_Observations",
        "Period_Start", "Period_End", "Industries_Included", "Industries_Excluded",
        "Listing_Requirement", "Data_Sources",
        "Data_Overlap_With_Ours", "Sample_Selection_Notes", "Survivorship_Bias_Addressed",
    ],
    # 6_THEORY is dynamic — built per config
    "7_FINDINGS": [
        "PAPER_ID", "Main_Finding", "Effect_Direction",
        "Coefficient_Beta", "Standard_Error", "P_Value",
        "Economic_Significance", "Moderating_Effects_Found", "Mediating_Effects_Found",
        "Heterogeneity_Results", "Contradictions_With_Literature",
        "Mechanisms_Channels_Identified",
    ],
    "8_GAPS_LIMITATIONS": [
        "PAPER_ID",
        "Stated_Limitation_1", "Stated_Limitation_2", "Stated_Limitation_3",
        "Future_Research_1", "Future_Research_2", "Future_Research_3",
        "OUR_Theoretical_Gap", "OUR_Methodological_Gap", "OUR_Variable_Gap",
        "OUR_Contextual_Gap", "OUR_Mechanism_Gap",
        "What_To_Adopt", "What_To_Avoid", "Our_Critical_Assessment",
    ],
    "9_RELEVANCE": [
        "PAPER_ID", "Topic_Alignment", "Variable_Usefulness",
        "Methodological_Value", "Theoretical_Contribution", "Recency",
        "Publication_Quality", "Weighted_Score", "Relevance_Tier",
        "Scoring_Justification",
    ],
    "10_CLASSIFICATION": [
        "PAPER_ID", "Primary_Theme", "Secondary_Theme", "Paper_Assignment",
        "Use_Case_Theory", "Use_Case_Methodology", "Use_Case_Variables",
        "Use_Case_Measurement", "Use_Case_Context", "Use_Case_Gaps",
        "Use_Case_H_Support", "Use_Case_H_Contradict",
        "Gap_Cluster",
        "Informs_Our_IV", "Informs_Our_DV",
        "Suggests_Moderators", "Suggests_Mediators", "Suggests_Controls",
    ],
    # 11_CONNECTIONS is dynamic — built per config
}

STATIC_TAIL = {
    "GAP_TRACKER": [
        "Gap_ID", "Gap_Type", "Gap_Statement", "Severity", "Feasibility",
        "Novelty", "Priority_Score", "Source_Paper_IDs", "Paper_Assignment",
        "Potential_Hypothesis", "Variables_Needed", "Methodology_Needed",
        "Data_Available", "Status", "Notes", "Coverage_Level",
        "Covering_Paper_IDs", "Coverage_Notes",
    ],
    "GAP_EVIDENCE": [
        "Gap_ID", "Paper_ID", "Pct_Eliminated", "Pct_Remaining_Before",
        "Pct_Remaining_After", "Aspect_Addressed", "What_Still_Remains",
        "Assessed_By", "Assessed_At", "Source",
    ],
}


def _build_theory_columns(config: ResearchConfig) -> list[str]:
    cols = [
        "PAPER_ID", "Primary_Theory", "Secondary_Theory_1", "Secondary_Theory_2",
        "Theory_Application_Quality", "Theoretical_Predictions_Tested",
        "Theoretical_Contribution",
    ]
    for s in config.key_scholars:
        cols.append(f"Cites_{s.key}")
        cols.append(f"{s.key}_Paper_Cited")
    cols.append("Connection_To_Our_Theories")
    return cols


def _build_connections_columns(config: ResearchConfig) -> list[str]:
    cols = ["PAPER_ID"]
    for s in config.key_scholars:
        cols.append(f"Cites_{s.key}")
        cols.append(f"{s.key}_Paper_Cited")
    cols.extend([
        "Important_Refs_To_Add", "Related_Papers_In_DB",
        "Builds_On", "Contradicts",
        "Replication_Possible_With_Our_Data", "Replication_Notes",
    ])
    return cols


def _build_custom_section_columns(config: ResearchConfig) -> dict[str, list[str]]:
    result = {}
    for sec in config.custom_sections:
        cols = ["PAPER_ID"]
        for col in sec.columns:
            cols.append(col.name)
        result[sec.id] = cols
    return result


def _format_list(items: list[str], indent: int = 8) -> str:
    """Format a Python list literal across multiple lines."""
    pad = " " * indent
    lines = []
    for item in items:
        lines.append(f'{pad}"{item}",')
    return "\n".join(lines)


def generate(config: ResearchConfig, output_path: str = "schemas.py") -> None:
    """Generate schemas.py from a ResearchConfig."""

    # Build dynamic sections
    theory_cols = _build_theory_columns(config)
    connections_cols = _build_connections_columns(config)
    custom_cols = _build_custom_section_columns(config)

    # Build all columns in order
    all_sections = {}
    # Static 1-5
    for key in ["1_IDENTIFICATION", "2_RESEARCH_DESIGN", "3_VARIABLES", "4_METHODOLOGY", "5_SAMPLE"]:
        all_sections[key] = STATIC_COLUMNS[key]
    # Dynamic 6
    all_sections["6_THEORY"] = theory_cols
    # Static 7-10
    for key in ["7_FINDINGS", "8_GAPS_LIMITATIONS", "9_RELEVANCE", "10_CLASSIFICATION"]:
        all_sections[key] = STATIC_COLUMNS[key]
    # Dynamic 11
    all_sections["11_CONNECTIONS"] = connections_cols
    # Custom sections
    for sec_id, cols in custom_cols.items():
        all_sections[sec_id] = cols
    # GAP_TRACKER + GAP_EVIDENCE
    for key in ["GAP_TRACKER", "GAP_EVIDENCE"]:
        all_sections[key] = STATIC_TAIL[key]

    # Build extraction sections list (everything except GAP_TRACKER, GAP_EVIDENCE)
    extraction_sections = [k for k in all_sections if k not in ("GAP_TRACKER", "GAP_EVIDENCE")]

    # Relevance score fields for validation
    relevance_fields = [d.name for d in config.relevance_rubric.dimensions]

    # Generate file content
    lines = [
        '"""',
        'PhD Literature Extraction Pipeline \u2014 Schemas',
        '==============================================',
        'Defines the extraction JSON structure and validation.',
        'Column-order lists for Google Sheets population.',
        '',
        'AUTO-GENERATED by codegen/generate_schemas.py',
        'Do not edit manually \u2014 re-run the generator instead.',
        '"""',
        'from __future__ import annotations',
        '',
        '',
        '# \u2500\u2500\u2500 COLUMN ORDERS PER TAB \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500',
        '# These define the exact column order for each Google Sheet tab.',
        '# Used by populator.py to construct rows.',
        '',
        'COLUMNS = {',
    ]

    for sec_id, cols in all_sections.items():
        lines.append(f'    "{sec_id}": [')
        lines.append(_format_list(cols))
        lines.append('    ],')

    # Add comment before GAP_TRACKER if present
    lines.append('}')
    lines.append('')

    # EXTRACTION_SECTIONS
    lines.append('# Sections that map to sheet tabs (the extraction JSON keys)')
    lines.append('EXTRACTION_SECTIONS = [')
    for sec in extraction_sections:
        lines.append(f'    "{sec}",')
    lines.append(']')
    lines.append('')
    lines.append('')

    # validate_extraction
    lines.append('# \u2500\u2500\u2500 VALIDATION \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500')
    lines.append('')
    lines.append('def validate_extraction(data: dict) -> tuple[bool, list[str]]:')
    lines.append('    """')
    lines.append('    Validate extracted JSON has required structure.')
    lines.append('    Returns (is_valid, list_of_errors).')
    lines.append('    """')
    lines.append('    errors = []')
    lines.append('')
    lines.append('    # Must have paper_id')
    lines.append('    if not data.get("paper_id"):')
    lines.append('        errors.append("Missing paper_id")')
    lines.append('')
    lines.append('    # Must have all extraction sections')
    lines.append('    for section in EXTRACTION_SECTIONS:')
    lines.append('        if section not in data:')
    lines.append('            errors.append(f"Missing section: {section}")')
    lines.append('        elif not isinstance(data[section], dict):')
    lines.append('            errors.append(f"Section {section} must be a dict, got {type(data[section]).__name__}")')
    lines.append('')
    lines.append('    # Must have gap_analysis')
    lines.append('    if "gap_analysis" not in data:')
    lines.append('        errors.append("Missing gap_analysis")')
    lines.append('    else:')
    lines.append('        ga = data["gap_analysis"]')
    lines.append('        if not isinstance(ga, dict):')
    lines.append('            errors.append("gap_analysis must be a dict")')
    lines.append('        else:')
    lines.append('            if "existing_gaps_updated" not in ga:')
    lines.append('                errors.append("Missing gap_analysis.existing_gaps_updated")')
    lines.append('            if "new_gaps_identified" not in ga:')
    lines.append('                errors.append("Missing gap_analysis.new_gaps_identified")')
    lines.append('')
    lines.append('    # Must have narrative_assessment')
    lines.append('    if not data.get("narrative_assessment"):')
    lines.append('        errors.append("Missing narrative_assessment")')
    lines.append('')
    lines.append('    # Validate PAPER_ID consistency')
    lines.append('    pid = data.get("paper_id", "")')
    lines.append('    for section in EXTRACTION_SECTIONS:')
    lines.append('        if section in data and isinstance(data[section], dict):')
    lines.append('            section_pid = data[section].get("PAPER_ID", "")')
    lines.append('            if section_pid and section_pid != pid:')
    lines.append('                errors.append(f"{section}.PAPER_ID (\'{section_pid}\') != paper_id (\'{pid}\')")')
    lines.append('')
    lines.append('    # Validate relevance scores are numeric')
    lines.append('    if "9_RELEVANCE" in data and isinstance(data["9_RELEVANCE"], dict):')
    lines.append('        rel = data["9_RELEVANCE"]')

    # Relevance fields from rubric
    rel_fields_str = ", ".join(f'"{f}"' for f in relevance_fields)
    lines.append(f'        for field in [{rel_fields_str}]:')
    lines.append('            val = rel.get(field)')
    lines.append('            if val is not None and not isinstance(val, (int, float)):')
    lines.append('                errors.append(f"9_RELEVANCE.{{field}} must be numeric, got {type(val).__name__}")')
    lines.append('')
    lines.append('    is_valid = len(errors) == 0')
    lines.append('    return is_valid, errors')
    lines.append('')

    output = Path(output_path)
    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generated {output.resolve()}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate schemas.py from research config")
    parser.add_argument("--config", default="research_config.yaml", help="Path to research_config.yaml")
    parser.add_argument("--output", default="schemas.py", help="Output path")
    args = parser.parse_args()

    cfg = load_config(args.config)
    generate(cfg, args.output)
