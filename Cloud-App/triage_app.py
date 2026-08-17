# triage_app.py — run locally:  python -m streamlit run triage_app.py
import streamlit as st
import json
from pathlib import Path

# Streamlit Community Cloud starts every app from the REPO ROOT, even when
# the entrypoint lives in a subfolder. Anchor data files to this script's
# own directory so relative opens work locally and when deployed.
APP_DIR = Path(__file__).parent

st.set_page_config(page_title="Rural Triage Support", layout="wide")

# --- Demonstration banner (non-negotiable) ---
st.error("⚠ DEMONSTRATION ONLY — SYNTHETIC DATA (Synthea FHIR R4). "
         "NOT FOR CLINICAL USE. Decision support, not diagnosis.")

st.title("Rural Triage & Diagnostic Support")
st.caption("Proof of concept — ingests standard FHIR R4 resources, surfaces "
           "flags for clinician review.")

with open(APP_DIR / 'triage_cohort.json') as f:
    cohort = json.load(f)

# --- View selector (patient triage vs. site sustainability) ---
view = st.sidebar.radio("View", ["Patient Triage", "Site Sustainability"])

if view == "Patient Triage":
    # --- Patient selector ---
    case_display_map = {
        "Pediatric": "Pediatric",
        "Healthy adult": "Healthy Adult",
        "Complex geriatric": "Complex Geriatric",
        "Allergy carrier": "Allergy Carrier",
        "High medication": "High Medication",
    }
    reverse_case_map = {v: k for k, v in case_display_map.items()}
    
    selected_display_case = st.sidebar.radio(
        "Select Patient Case", 
        list(case_display_map.values())
    )
    case = reverse_case_map[selected_display_case]
    p = cohort[case]

    # --- Header ---
    st.header(f"{p['name']}")
    c1, c2, c3 = st.columns(3)
    c1.metric("Age", p['age'])
    c2.metric("Sex", p['gender'].capitalize())
    c3.metric("Active Conditions", len(p['conditions']))

    # --- Safety Flags FIRST (most important) ---
    st.subheader("Safety Flags")
    if not p['flags']:
        st.success("No Flags — Record Clear")
    for fl in p['flags']:
        line = f"**{fl['kind']}** — {fl['msg']}"
        if fl['severity'] == 'high':
            st.error(line)
        elif fl['severity'] == 'medium':
            st.warning(line)
        else:
            st.info(line)

    # --- Allergies (safety-critical, prominent) ---
    st.subheader("Allergies")
    if p['allergies']:
        for a in p['allergies']:
            st.markdown(f"🔴 **{a}**")
    else:
        st.write("None Recorded")

    # --- Vitals ---
    st.subheader("Vitals")
    if p['vitals']:
        for v in p['vitals']:
            flag = f" ⚠ {v['flag']}" if v['flag'] else ""
            st.write(f"**{v['label'].title()}:** {v['value']} {v['unit']}{flag}  "
                     f"_(Recorded {v['date'][:10]})_")
    else:
        st.write("No Vitals Recorded")

    # --- Conditions & meds side by side ---
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader(f"Active Problems ({len(p['conditions'])})")
        for c in p['conditions']:
            st.write(f"• {c}")
    with col_b:
        st.subheader(f"Medications ({len(p['medications'])})")
        for m in p['medications'][:20]:
            st.write(f"• {m}")
        if len(p['medications']) > 20:
            st.caption(f"...and {len(p['medications'])-20} More")

    # --- Encounter value estimate (per patient) ---
    # Chain: SNOMED -> ICD-10 -> MDC -> DRG weight range -> estimate.
    # Loads per-case output of the diagnostic notebook if present; falls
    # back to the documented 4 Aug 2026 cohort run.
    COHORT_RECORD = {   # 4 Aug 2026 run: (MDC, mapped, total, estimate)
        "Pediatric":         ("01 Nervous",      2,  3, 14232),
        "Healthy adult":     (None,              0,  0, None),
        "Complex geriatric": ("05 Circulatory", 13, 28, 21922),
        "Allergy carrier":   ("03 ENT",          1,  7,  9959),
        "High medication":   ("05 Circulatory", 15, 23, 21922),
    }
    try:
        with open(APP_DIR / 'reimbursement_estimates.json') as f:
            est_file = json.load(f)
        est_src = "Diagnostic Notebook Output"
    except FileNotFoundError:
        est_file = {}
        est_src = "4 Aug 2026 Cohort Run (Documented Record)"

    st.subheader("Encounter Value Estimate")
    st.caption("**Estimate of Clinical Resource Intensity — NOT Payment.** "
               "MDC-level approximation; CAHs and REHs are cost-reimbursed. "
               f"Source: {est_src}.")
    mdc, mapped, total_c, fallback_val = COHORT_RECORD.get(
        case, (None, 0, 0, None))
    value = est_file.get(case, fallback_val)
    if value is None:
        st.info("No Mapped Billable Conditions — No Estimate Produced. "
                "(This is the conservative behavior, not an error.)")
    else:
        v1, v2 = st.columns(2)
        v1.metric("Encounter Value Estimate", f"${value:,.0f}")
        v2.metric("MDC", mdc)
        st.caption(f"Mapping Coverage: {mapped} of {total_c} Conditions "
                   "Mapped to Billable ICD-10 Codes; Estimates Are "
                   "Conservative. MDC Method Distinguishes Body Systems, "
                   "Not Severity — Cases Sharing an MDC Share an Estimate.")
    st.caption("↳ These Per-Encounter Values, Weighted by County Demand, "
               "Roll Up Into the **Site Sustainability** View.")

else:
    # =========================================================================
    # SITE SUSTAINABILITY PANEL
    # Reads site_feasibility.json produced by the main notebook (Panel 3).
    # =========================================================================
    st.warning("**Encounter Value Estimate — NOT Payment or Revenue.** "
               "Quantifies clinical resource intensity for sustainability "
               "framing. CAHs and REHs are cost-reimbursed / receive facility "
               "payments.")
    try:
        with open(APP_DIR / 'site_feasibility.json') as f:
            sf = json.load(f)
    except FileNotFoundError:
        st.info("Run Panel 3 in the main notebook to generate "
                "`site_feasibility.json`, then place it beside this app.")
        st.stop()

    st.header(f"Candidate Site: {sf['site']}")
    st.caption(f"MCDA Rank #1 Under Equity and Balanced Weightings · "
               f"Population {sf['county_population']:,} "
               f"({sf['population_vintage']})")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Expected ED Encounters / Yr", f"{sf['annual_ed_encounters']:,}")
    c2.metric("Per Day", sf['encounters_per_day'])
    c3.metric("Admission-Level Acuity / Yr", sf['admission_level_per_year'])
    c4.metric("Transfer-Level / Yr", sf['transfer_level_per_year'])

    st.subheader("Annual Encounter Value Envelope")
    st.caption("Admission-Level Encounters Only (11.5% of Visits, NHAMCS 2022). "
               f"Per-Archetype Estimates: {sf['estimates_source']}.")
    e1, e2, e3 = st.columns(3)
    e1.metric("Low", f"${sf['envelope_low']:,}")
    e2.metric("Medium", f"${sf['envelope_central']:,}")
    e3.metric("High", f"${sf['envelope_high']:,}")

    st.subheader("Population by Age Band")
    st.bar_chart(sf['age_bands'])

    st.subheader("Funding Pathway (NM Rural Health Transformation Program)")
    st.markdown(
        "| RHT Stream | Project Component |\n"
        "|---|---|\n"
        "| Rural Health Innovation Fund | MCDA Siting Analysis (This Site) |\n"
        "| Healthy Horizons | Triage & Diagnostic Support Tool |\n"
        "| Rooted in New Mexico | Workforce Arm of the Systems Loop |\n"
        "| Rural Health Data Hub | County-Level Analytical Frame |\n"
    )
    st.caption("NM RHT: $211.5M Awarded for FFY2026, Program Runs 2026–2030 "
               "(NM Health Care Authority). The Gap Between the Encounter "
               "Value Envelope and Operating Cost Is the Quantified Funding "
               "Ask — Not a Weakness of the Proposal.")

    st.subheader("Caveats (Stated)")
    for cv in sf['caveats']:
        st.markdown(f"- {cv}")
