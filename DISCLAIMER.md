# DearNana — Disclaimers and Limitations

---

## 1. Not Medical or Legal Advice

DearNana is an informational tool that surfaces publicly available government data. It is **NOT** a substitute for professional medical advice, legal counsel, or in-person facility evaluation.

The composite score is a starting point for research — it is not a recommendation to place a family member in any specific facility. Nursing home selection is a complex, deeply personal decision that depends on factors well beyond what any dataset can capture.

Always consult qualified healthcare professionals (physicians, social workers, geriatric care managers) before making placement decisions. Always visit facilities in person and speak with staff and current residents' families before signing any agreement.

---

## 2. Data Source and Accuracy

- All facility data is sourced from the **CMS Provider Data Catalog** (https://data.cms.gov/provider-data/topics/nursing-homes), which CMS refreshes monthly.
- DearNana caches data locally for up to 24 hours to reduce API load — cached data may be up to 24 hours old at the time of your search.
- CMS data itself may lag real-world conditions by weeks to months, particularly for recent inspection findings, staffing changes, or newly levied penalties.
- DearNana does **not** independently verify CMS data. Errors, omissions, or outdated information in the CMS source will appear in DearNana output.
- **Facility costs** shown are state-level monthly medians for semi-private rooms from the CareScout (Genworth Financial) Cost of Care Survey 2024 (surveyed July–December 2024; https://www.carescout.com/cost-of-care). These are **not** facility-specific prices — actual costs vary significantly by facility, room type, and care level. Contact facilities directly for current rates. Many facilities accept Medicaid; eligibility is determined separately.

---

## 3. Scoring Methodology Limitations

- The composite score is based on **quantitative CMS metrics only**. It cannot capture subjective quality factors such as facility culture, staff warmth, food quality, activity programming, family communication practices, or the general environment.
- Scoring weights (e.g., 25% for overall rating, 20% for health inspections) are set by the DearNana project and represent one reasonable interpretation of available evidence. Reasonable people — including healthcare professionals — may weight these factors differently based on individual circumstances.
- Facilities with **missing data fields** receive a neutral score (50 out of 100) for those components. This may artificially inflate or deflate their overall ranking compared to fully-reported facilities.
- **Distance scoring** assumes that closer is generally preferable for family visits and continuity of care. This may not reflect your actual situation (e.g., if you prefer a specific facility farther away for clinical reasons).
- The **abuse flag deduction** (−50 points) is based on CMS's own abuse icon designation. DearNana applies this as a near-disqualifying penalty, which reflects the severity of the finding. However, the underlying CMS record should always be reviewed directly at https://www.medicare.gov/care-compare before drawing conclusions.

---

## 4. AI-Generated Recommendations

- When AI is enabled with the default provider (an `ANTHROPIC_API_KEY` is set and `--no-ai` is not used), DearNana sends your care condition description to the **Anthropic Claude API** twice: once to parse it into a structured needs profile that personalizes the ranking, and once to generate the personalized recommendation report.
- The condition description you provide is transmitted to Anthropic's servers and is subject to their privacy policy: https://www.anthropic.com/privacy
- You bring your own API key — DearNana never proxies your data through any server operated by the project. The only third parties contacted are CMS (facility data), OpenStreetMap Nominatim (geocoding your search address), and Anthropic (when AI is enabled with the default provider).
- **Local alternative:** with `DEARNANA_LLM_PROVIDER=ollama`, all AI processing runs on your own machine via a local model and your condition description is never transmitted to any AI provider. AI quality depends on the local model you choose.
- AI output is generated from the CMS data described above — it does not incorporate real-time information, facility-specific knowledge, or clinical assessment.
- AI-generated recommendations should be treated as a **structured summary of public data**, not a clinical assessment or professional referral.
- Use the `--no-ai` flag to skip all Anthropic API calls entirely. The ranked list — including condition-based personalization via built-in keyword matching — is still produced using CMS data only, and your condition description never leaves your machine.

---

## 5. No Financial Relationships

DearNana has no financial relationship with any nursing home, senior care network, placement service, referral agency, or healthcare organization. Facilities **cannot pay** to improve their scores or appear in results. Rankings are determined solely by the algorithm described in [README.md](README.md).

This tool was built to counter the opacity of for-profit referral networks that often steer families toward facilities that pay the highest referral fees rather than those that best fit their needs.

---

## 6. Liability

THE SOFTWARE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND NONINFRINGEMENT.

THE AUTHORS AND CONTRIBUTORS OF DEARNANA DISCLAIM ALL LIABILITY FOR ANY DECISIONS, ACTIONS, OR OUTCOMES THAT RESULT FROM USE OF THIS TOOL OR RELIANCE ON ITS OUTPUT. THIS INCLUDES, WITHOUT LIMITATION, ANY HARM ARISING FROM NURSING HOME PLACEMENT DECISIONS INFORMED IN WHOLE OR IN PART BY DEARNANA'S SCORES, RANKINGS, OR AI-GENERATED REPORTS.

USE THIS TOOL AT YOUR OWN RISK. IT IS A STARTING POINT FOR RESEARCH — NOT A SUBSTITUTE FOR PROFESSIONAL ADVICE OR IN-PERSON EVALUATION.

---

*Last updated: June 2026*
