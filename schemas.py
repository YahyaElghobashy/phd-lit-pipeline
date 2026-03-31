"""
PhD Literature Extraction Pipeline — Schemas
==============================================
Defines the extraction JSON structure and validation.
Column-order lists for Google Sheets population.
"""
from __future__ import annotations


# ─── COLUMN ORDERS PER TAB ──────────────────────────────────
# These define the exact column order for each Google Sheet tab.
# Used by populator.py to construct rows.

COLUMNS = {
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
    "6_THEORY": [
        "PAPER_ID", "Primary_Theory", "Secondary_Theory_1", "Secondary_Theory_2",
        "Theory_Application_Quality", "Theoretical_Predictions_Tested",
        "Theoretical_Contribution",
        "Cites_Adams", "Adams_Paper_Cited",
        "Cites_Eagly", "Eagly_Paper_Cited",
        "Connection_To_Our_Theories",
    ],
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
    # NOTE: Sheet headers for 9_RELEVANCE have suffixes like "(25%)" but
    # we write by position, not by header name, so our field names work fine.
    "10_CLASSIFICATION": [
        "PAPER_ID", "Primary_Theme", "Secondary_Theme", "Paper_Assignment",
        "Use_Case_Theory", "Use_Case_Methodology", "Use_Case_Variables",
        "Use_Case_Measurement", "Use_Case_Context", "Use_Case_Gaps",
        "Use_Case_H_Support", "Use_Case_H_Contradict",
        "Gap_Cluster",
        "Informs_Our_IV", "Informs_Our_DV",
        "Suggests_Moderators", "Suggests_Mediators", "Suggests_Controls",
    ],
    "11_CONNECTIONS": [
        "PAPER_ID", "Cites_Adams", "Adams_Paper_Cited",
        "Cites_Eagly", "Eagly_Paper_Cited",
        "Important_Refs_To_Add", "Related_Papers_In_DB",
        "Builds_On", "Contradicts",
        "Replication_Possible_With_Our_Data", "Replication_Notes",
    ],
    "12_BOARD_CHARS": [
        "PAPER_ID",
        "Gender_Diversity_Examined", "Board_Size_Examined", "Board_Independence_Examined",
        "CEO_Chair_Duality_Examined", "Director_Age_Examined", "Director_Tenure_Examined",
        "Education_Level_Examined", "Education_Field_Examined", "Busyness_Examined",
        "Exec_vs_NonExec_Examined", "Nationality_Intl_Examined",
        "Functional_Background_Examined", "Years_Experience_Examined",
        "Time_To_Retirement_Examined", "Network_Centrality_Examined",
        "Committee_Membership_Examined", "Meeting_Frequency_Examined",
        "Board_Compensation_Examined",
        "Director_vs_Board_Level", "Gender_X_Char_Interactions",
        "Critical_Mass_Tested", "Critical_Mass_Result",
        "Missing_Chars_From_Our_Framework",
    ],
    # Actual sheet column order for GAP_TRACKER:
    # Gap_ID, Gap_Type, Gap_Statement, Severity (1-5), Feasibility (1-5),
    # Novelty (1-5), Priority_Score, Source_Paper_IDs, Paper_Assignment,
    # Potential_Hypothesis, Variables_Needed, Methodology_Needed,
    # Data_Available, Status, Notes, Coverage_Level, Covering_Paper_IDs, Coverage_Notes
    "GAP_TRACKER": [
        "Gap_ID", "Gap_Type", "Gap_Statement", "Severity", "Feasibility",
        "Novelty", "Priority_Score", "Source_Paper_IDs", "Paper_Assignment",
        "Potential_Hypothesis", "Variables_Needed", "Methodology_Needed",
        "Data_Available", "Status", "Notes", "Coverage_Level",
        "Covering_Paper_IDs", "Coverage_Notes",
        # Taxonomy columns (Phase 2 overhaul)
        "Tier", "Tier_Justification", "Tier_Set_By", "Tier_Set_At",
    ],
    "GAP_EVIDENCE": [
        "Gap_ID", "Paper_ID", "Pct_Eliminated", "Pct_Remaining_Before",
        "Pct_Remaining_After", "Aspect_Addressed", "What_Still_Remains",
        "Reasoning",  # Full AI reasoning text (Phase 4 overhaul)
        "Assessed_By", "Assessed_At", "Source",
        # Confidence scoring (Module 6)
        "Confidence_Methodological", "Confidence_Sample",
        "Confidence_Variables", "Confidence_Directness",
        "Confidence_Overall", "Confidence_Tier",
    ],
}

# Sections that map to sheet tabs (the extraction JSON keys)
EXTRACTION_SECTIONS = [
    "1_IDENTIFICATION",
    "2_RESEARCH_DESIGN",
    "3_VARIABLES",
    "4_METHODOLOGY",
    "5_SAMPLE",
    "6_THEORY",
    "7_FINDINGS",
    "8_GAPS_LIMITATIONS",
    "9_RELEVANCE",
    "10_CLASSIFICATION",
    "11_CONNECTIONS",
    "12_BOARD_CHARS",
]


# ─── VALIDATION ─────────────────────────────────────────────

def validate_extraction(data: dict) -> tuple[bool, list[str]]:
    """
    Validate extracted JSON has required structure.
    Returns (is_valid, list_of_errors).
    """
    errors = []

    # Must have paper_id
    if not data.get("paper_id"):
        errors.append("Missing paper_id")

    # Must have all 12 sections
    for section in EXTRACTION_SECTIONS:
        if section not in data:
            errors.append(f"Missing section: {section}")
        elif not isinstance(data[section], dict):
            errors.append(f"Section {section} must be a dict, got {type(data[section]).__name__}")

    # Must have gap_analysis
    if "gap_analysis" not in data:
        errors.append("Missing gap_analysis")
    else:
        ga = data["gap_analysis"]
        if not isinstance(ga, dict):
            errors.append("gap_analysis must be a dict")
        else:
            if "existing_gaps_updated" not in ga:
                errors.append("Missing gap_analysis.existing_gaps_updated")
            if "new_gaps_identified" not in ga:
                errors.append("Missing gap_analysis.new_gaps_identified")

    # Must have narrative_assessment
    if not data.get("narrative_assessment"):
        errors.append("Missing narrative_assessment")

    # Validate PAPER_ID consistency
    pid = data.get("paper_id", "")
    for section in EXTRACTION_SECTIONS:
        if section in data and isinstance(data[section], dict):
            section_pid = data[section].get("PAPER_ID", "")
            if section_pid and section_pid != pid:
                errors.append(f"{section}.PAPER_ID ('{section_pid}') != paper_id ('{pid}')")

    # Validate relevance scores are numeric
    if "9_RELEVANCE" in data and isinstance(data["9_RELEVANCE"], dict):
        rel = data["9_RELEVANCE"]
        for field in ["Topic_Alignment", "Variable_Usefulness", "Methodological_Value",
                       "Theoretical_Contribution", "Recency", "Publication_Quality"]:
            val = rel.get(field)
            if val is not None and not isinstance(val, (int, float)):
                errors.append(f"9_RELEVANCE.{field} must be numeric, got {type(val).__name__}")

    is_valid = len(errors) == 0
    return is_valid, errors
