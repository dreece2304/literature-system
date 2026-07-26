"""Unified extraction prompts for LLM-based paper analysis.

This module contains the extraction prompts used by both Ollama and Claude
for consistent paper extraction quality.

Two-Tier Extraction System:
    - Quick: Abstract-only extraction for all papers (fast categorization)
    - Deep: Full-text extraction for selected papers (2-pass: chunks → consolidation)

Usage:
    from services.extraction_prompts import (
        get_extraction_prompt,
        get_chunk_extraction_prompt,
        get_consolidation_prompt,
        EXTRACTION_SCHEMA,
    )

    # Quick extraction (title + abstract + journal)
    prompt = get_extraction_prompt(title, abstract, tier="quick", journal=journal)

    # Deep extraction - Pass 1: Process each chunk
    for i, chunk in enumerate(chunks, 1):
        prompt = get_chunk_extraction_prompt(title, chunk, i, len(chunks),
                                              prior_context=state.to_prompt_context())
        chunk_result = llm(prompt)
        chunk_extractions.append(chunk_result)

    # Deep extraction - Pass 2: Consolidate chunks
    prompt = get_consolidation_prompt(
        title, abstract, quick_extraction, chunk_extractions,
        journal=journal, authors=authors, year=year
    )
    final_result = llm(prompt)
"""

from __future__ import annotations
from typing import Literal, Optional


# =============================================================================
# Extraction Schema Definition
# =============================================================================

EXTRACTION_SCHEMA = {
    "quick": {
        "required": ["paper_type", "topics", "one_sentence_summary"],
        "optional": [],
        "description": "Fast categorization using title, journal, and abstract",
        "paper_types": [
            "research_article", "review", "perspective", "letter",
            "conference", "thesis", "book_chapter", "patent", "other"
        ],
    },
    "chunk": {
        "required": ["section_type", "facts"],
        "optional": ["numbers", "methods", "materials", "claim_citations", "defined_terms", "sections_in_chunk"],
        "description": "Per-chunk raw data extraction for deep extraction pass 1",
        "section_types": [
            "introduction", "methods", "results", "discussion",
            "conclusion", "mixed", "other"
        ],
    },
    "deep": {
        "required": [
            "paper_type", "topics", "one_sentence_summary",
            "key_findings", "methodology_summary"
        ],
        "optional": [
            "quantitative_results", "citable_claims", "techniques_used",
            "experimental_conditions", "discussion_summary", "research_context",
            "future_directions"
        ],
        "description": "Comprehensive extraction from full paper text",
        "paper_types": [
            "research_article", "review", "perspective", "letter",
            "conference", "thesis", "book_chapter", "patent", "other"
        ],
    },
}


# =============================================================================
# Quick Tier Prompt (Title + Abstract + Journal)
# =============================================================================

QUICK_EXTRACTION_PROMPT = '''You are a scientific literature analyst extracting metadata to enable paper search and categorization.

PAPER TITLE: {title}

JOURNAL: {journal}

ABSTRACT: {abstract}

Extract the following in JSON format:

{{
    "paper_type": "<type>",
    "topics": ["<topic1>", "<topic2>", "<topic3>", ...],
    "one_sentence_summary": "<summary>"
}}

================================================================================
FIELD 1: paper_type
================================================================================

Select ONE type based on content. Use journal name as a hint but prioritize content.

"research_article" - Original research (most common, ~70%):
  - Has hypothesis, methods, new data/results
  - Journals: Nature, Science, JACS, ACS Nano, Advanced Materials, etc.

"review" - Survey of existing literature:
  - Summarizes multiple studies, no new experimental data
  - Look for: "review", "survey", "overview", "state-of-the-art", "recent advances"
  - Journals: Chemical Reviews, Nature Reviews, Annual Review of..., Progress in...

"perspective" - Opinion/commentary piece:
  - Author viewpoint, shorter, less structured than reviews
  - Look for: "perspective", "opinion", "commentary", "viewpoint", "outlook"

"letter" - Short/rapid communication:
  - Brief format, preliminary or urgent results
  - Look for: "letter", "communication", "brief report", "rapid"
  - Journals: Applied Physics Letters, Nano Letters, ...Letters

"conference" - Conference proceedings:
  - Look for: "proceedings", "conference", symposium references
  - Journals: Proc. SPIE, IEEE proceedings, MRS Advances

"thesis" - Dissertation or thesis chapter
"book_chapter" - Chapter from edited book
"patent" - Patent document
"other" - Only if none above fit

================================================================================
FIELD 2: topics
================================================================================

Array of 3-5 topics as NOUN PHRASES, ordered from broad to specific.

HIERARCHY:
1. Research field (broad): "materials science", "surface chemistry", "nanofabrication"
2. Subfield: "thin film deposition", "photolithography", "surface analysis"
3. Technique/method: "atomic layer deposition", "EUV lithography", "XPS"
4. Materials/systems: "aluminum oxide", "photoresist", "high-k dielectrics"
5. Application (if clear): "semiconductor manufacturing", "flexible electronics"

FORMAT RULES:
- Use lowercase unless proper noun (e.g., "Fourier transform", "Monte Carlo")
- Noun phrases only ("film growth" not "growing films")
- Be specific: "X-ray photoelectron spectroscopy" not "surface analysis"

DOMAIN EXAMPLES:

Materials Science / Thin Films:
- "atomic layer deposition" → "plasma-enhanced ALD" → "Al2O3" → "high-k dielectrics"
- "molecular layer deposition" → "hybrid films" → "alucone" → "flexible barriers"
- "chemical vapor deposition" → "MOCVD" → "III-V semiconductors"

Lithography / Nanofabrication:
- "lithography" → "EUV lithography" → "photoresist" → "chemically amplified resists"
- "nanoimprint lithography" → "pattern transfer" → "template fabrication"
- "directed self-assembly" → "block copolymers" → "line-space patterns"

Characterization Techniques:
- "X-ray photoelectron spectroscopy" → "XPS peak fitting" → "binding energies"
- "time-of-flight SIMS" → "ToF-SIMS fragmentation" → "organic fragment analysis"
- "spectroscopic ellipsometry" → "optical constants" → "thin film metrology"
- "FTIR spectroscopy" → "surface species identification" → "reaction mechanisms"

Surface Science / Fundamentals:
- "surface chemistry" → "adsorption mechanisms" → "ligand exchange"
- "reaction kinetics" → "growth mechanisms" → "nucleation"

Other Fields (brief):
- Biology: "biochemistry" → "protein structure" → "X-ray crystallography"
- CS/ML: "machine learning" → "computer vision" → "convolutional neural networks"

BAD EXAMPLES (avoid):
- "study", "analysis", "investigation" (too generic)
- "novel method", "new approach" (not topics)
- "high performance", "improved" (descriptors, not topics)

================================================================================
FIELD 3: one_sentence_summary
================================================================================

One sentence (20-40 words) capturing the paper's main contribution.

FORMAT BY PAPER TYPE:

research_article:
"[Method/Approach] was used to [study/investigate/deposit] [system], [achieving/demonstrating/revealing] [key quantitative result if available]."
Example: "Plasma-enhanced ALD was used to deposit HfO2 at 80°C, achieving 1.2 Å/cycle growth rate with breakdown field exceeding 8 MV/cm."

review:
"This review [surveys/examines/synthesizes] [topic], covering [scope/timeframe] and [identifying gaps/highlighting trends/comparing approaches]."
Example: "This review surveys atomic layer deposition of high-k dielectrics for CMOS, covering thermal and plasma methods and identifying challenges for sub-2nm equivalent oxide thickness."

perspective:
"This perspective [discusses/examines/argues] [topic/issue], [proposing/recommending/highlighting] [viewpoint/direction]."
Example: "This perspective discusses the future of EUV lithography, arguing that stochastic defects require new resist chemistries beyond chemically amplified systems."

letter:
"[Key finding/achievement] is demonstrated in [system/context] using [brief method]."
Example: "Sub-nanometer thickness control is demonstrated in MLD alucone films using in-situ ellipsometry feedback."

Default (if unsure):
"This work [investigates/presents/describes] [topic], [contributing/demonstrating/providing] [main contribution]."

AVOID:
- Starting with "This paper..." (redundant)
- Vague claims without specifics: "improved performance" (quantify if possible)
- Multiple sentences
- Exceeding 50 words

================================================================================
RULES (must follow)
================================================================================
- Output valid JSON only - no markdown, no code blocks, no explanation
- Use only the paper_type values listed above (use "other" only if truly none fit)
- topics must be an array with 3-5 items
- one_sentence_summary must be a single sentence
- Use null for fields where information is genuinely unavailable
- Do NOT fabricate information not present in the title/abstract

================================================================================
GUIDELINES (best practices)
================================================================================
- Use journal name to help infer paper_type, but content takes priority
- Topics should enable finding this paper via keyword search
- Summary should distinguish this paper from similar work
- If abstract is vague, make reasonable inference from title
- Use established scientific terminology

================================================================================
FINAL CHECK
================================================================================
Before outputting, verify:
- paper_type matches the actual content (not just journal name)
- All topics are actually discussed in the abstract
- Summary accurately reflects the abstract without over-claiming
- No information was added that isn't in the title/abstract

JSON:'''


# =============================================================================
# Chunk Extraction Prompt (Per-chunk processing for deep extraction)
# =============================================================================

CHUNK_EXTRACTION_PROMPT = '''You are extracting RAW DATA from a section of a scientific paper.
Your goal: Capture EVERYTHING factual from this chunk. Do NOT interpret or summarize - just extract.

This is chunk {chunk_number} of {total_chunks}.
PAPER: {title}

================================================================================
CONTEXT FROM EARLIER CHUNKS (facts only - do not repeat, use for continuity):
================================================================================
{prior_context}

================================================================================
CHUNK TEXT:
================================================================================
{chunk_text}

================================================================================
EXTRACT IN JSON FORMAT:
================================================================================
{{
    "section_type": "<type>",
    "sections_in_chunk": ["<section name(s) covered in this chunk>"],
    "facts": ["<fact1>", "<fact2>", ...],
    "numbers": [
        {{"value": "<number>", "unit": "<unit>", "what": "<what was measured>", "conditions": "<when/how>"}}
    ],
    "methods": ["<technique1>", "<technique2>", ...],
    "materials": ["<material1>", "<material2>", ...],
    "claim_citations": [
        {{"claim": "<claim text without citation>", "citation_numbers": [<n1>, <n2>], "claim_type": "<type>", "importance": "<level>"}}
    ],
    "defined_terms": {{"<abbreviation>": "<expansion>"}}
}}

================================================================================
FIELD INSTRUCTIONS:
================================================================================

section_type: What part of the paper is this? One of:
  "introduction", "methods", "results", "discussion", "conclusion", "mixed", "other"

sections_in_chunk: Named section heading(s) that appear in this chunk (e.g., ["Introduction"], ["Results", "Discussion"]).
  - Use the paper's own heading text when available; use an empty array [] if no clear heading is present.

facts: Main statements and findings. Extract ALL significant statements.
  - Quote directly or near-verbatim when possible
  - Include context (what, where, when, how)
  - Aim for 5-15 facts per chunk (more for results/methods sections)
  - BAD: "Good results were obtained" (vague)
  - GOOD: "The IMFP at 40 eV was measured to be 1.07 nm using the substrate-overlayer technique"

numbers: ALL quantitative data - every number, measurement, percentage, dimension.
  - value: The number (e.g., "1.2", "20-92", ">95%")
  - unit: The unit (e.g., "nm", "eV", "°C", "%", "Å/cycle")
  - what: What was measured (e.g., "mean free path", "temperature", "growth rate")
  - conditions: Context (e.g., "at 40 eV kinetic energy", "in photoresist films")
  - Include ALL numbers, not just "important" ones - err on the side of capturing more
  - Typical results section: 10-30 numbers

methods: Techniques, instruments, and characterization tools mentioned.
  - Include full names when given (e.g., "X-ray photoelectron spectroscopy" not just "XPS")
  - Include specific configurations if mentioned (e.g., "hemispherical electron analyzer")

materials: Chemicals, substrates, samples, precursors mentioned.
  - Include specific formulations (e.g., "poly hydroxystyrene-co-tertbutyl methacrylate")
  - Include substrate details (e.g., "Si(100) with native oxide")

claim_citations: Claims with explicit citation references [1], [17,23], (Smith 2020), etc.
  - claim: The exact claim text WITH the citation markers removed
  - citation_numbers: Array of reference numbers as integers (e.g., [17, 23])
  - claim_type: One of "fact", "method", "comparison", "limitation", "background"
  - importance: "high" (core result/claim), "medium" (supporting), "low" (background)

  EXAMPLES:
  Text: "ALD enables highly conformal coatings even on high-aspect-ratio structures [17, 23]."
  Output: {{"claim": "ALD enables highly conformal coatings even on high-aspect-ratio structures", "citation_numbers": [17, 23], "claim_type": "fact", "importance": "high"}}

  Text: "Previous studies have shown similar trends [5-7]."
  Output: {{"claim": "Previous studies have shown similar trends", "citation_numbers": [5, 6, 7], "claim_type": "background", "importance": "low"}}

  SKIP:
  - Generic citations without specific claims (e.g., "See methods in ref. [4]")
  - Citations in reference lists
  - Only extract 3-8 most significant cited claims per chunk

defined_terms: Abbreviations, acronyms, or entities defined or expanded in THIS chunk.
  - Map the short form to its full expansion as given in the text
  - Example: {{"DEZ": "diethylzinc", "4-MP": "4-mercaptophenol"}}
  - Use an empty object {{}} if nothing is defined in this chunk

================================================================================
GROUNDING REQUIREMENT:
================================================================================
facts and numbers MUST be captured VERBATIM (word-for-word quote) from the chunk
text above, not paraphrased or reconstructed from memory. If you cannot point to
the exact words in the chunk text supporting a fact or number, do not report it.

================================================================================
RULES:
================================================================================
- Extract from THIS CHUNK ONLY - do not infer from memory of other papers
- Use empty array [] for fields with no data in this chunk
- Preserve exact numbers and units from the text
- When in doubt, INCLUDE the data - consolidation will deduplicate later
- Output valid JSON only - no markdown, no explanation, no preamble

JSON:'''


# =============================================================================
# Consolidation Prompt (Synthesize chunk extractions into final schema)
# =============================================================================

CONSOLIDATION_PROMPT = '''You are synthesizing raw extracted data from paper chunks into a structured summary.

TASK: Consolidate ALL chunk data into a coherent final extraction. Your job is to:
1. DEDUPLICATE - Same data mentioned in multiple chunks → one entry
2. ORGANIZE - Group related information logically
3. SYNTHESIZE - Combine related facts into coherent findings
4. PRESERVE - Keep specific numbers and details, do not generalize

================================================================================
PAPER METADATA:
================================================================================
TITLE: {title}
JOURNAL: {journal}
AUTHORS: {authors}
YEAR: {year}

ABSTRACT:
{abstract}

================================================================================
QUICK EXTRACTION (from abstract - for reference):
================================================================================
{quick_extraction}

================================================================================
RAW CHUNK EXTRACTIONS (your source data):
================================================================================
{chunk_extractions}

================================================================================
OUTPUT SCHEMA - Fill ALL fields comprehensively:
================================================================================
{{
    "paper_type": "<research_article|review|letter|conference|other>",
    "topics": ["<topic1>", "<topic2>", "<topic3>", "<topic4>", "<topic5>"],
    "one_sentence_summary": "<WHAT was done + HOW + KEY RESULT with numbers>",
    
    "key_findings": [
        {{"finding": "<finding with specific numbers/results>", "quote": "<verbatim excerpt from chunk text/facts supporting this finding, max ~30 words>"}},
        {{"finding": "<finding with specific numbers/results>", "quote": "<verbatim excerpt from chunk text/facts supporting this finding, max ~30 words>"}},
        ...
    ],
    
    "methodology_summary": "<2-4 sentences: what technique, what samples, what conditions>",
    
    "quantitative_results": [
        {{"metric": "<what>", "value": "<number>", "unit": "<unit>", "conditions": "<context>"}}
    ],
    
    "citable_claims": [
        "<specific assertion that could support a citation>"
    ],
    
    "techniques_used": [
        {{"technique": "<name>", "purpose": "<why used>", "specifics": "<details if available>"}}
    ],
    
    "experimental_conditions": {{
        "materials": ["<material1>", "<material2>", ...],
        "temperature_range": "<range or null>",
        "pressure": "<range or null>",
        "key_parameters": ["<param1>", "<param2>", ...]
    }},
    
    "discussion_summary": "<2-3 sentences: main interpretation, comparison to prior work>",
    
    "research_context": {{
        "problem_addressed": "<what gap or problem>",
        "novelty": "<what is new about this work>",
        "limitations": "<acknowledged limitations>",
        "significance": "<why it matters>"
    }},
    
    "future_directions": ["<direction1>", "<direction2>", ...]
}}

================================================================================
FIELD-BY-FIELD GUIDANCE:
================================================================================

key_findings: Synthesize facts from chunks into 5-10 distinct findings.
  - Each finding should be specific with numbers when available
  - Combine related facts (e.g., if IMFP measured at multiple energies → one finding covering the range)
  - GOOD: "The IMFP ranged from 1-2 nm for kinetic energies 20-92 eV, increasing to 3-4 nm at higher energies"
  - BAD: "The mean free path was measured" (too vague)
  - Each finding is an object with a "finding" field and a "quote" field
  - "quote" MUST be copied verbatim (unchanged) from the chunk data (facts/numbers) that
    supports the finding - do not paraphrase inside "quote"
  - If no chunk data verbatim-supports a finding, do not include that finding

quantitative_results: Consolidate ALL numbers from chunk extractions.
  - Deduplicate (same measurement mentioned twice → one entry)
  - Keep the most specific/detailed version when duplicates exist
  - Include 8-20 results for a typical research paper
  - Every significant number from the paper should appear here

citable_claims: Extract 4-8 strong, specific assertions.
  - These are statements someone could cite this paper for
  - Must be supported by data in the paper
  - GOOD: "The presence of photoacid generator did not affect the electron mean free path within experimental error"
  - BAD: "EUV lithography is important" (obvious, not citable)

techniques_used: List all characterization and fabrication methods.
  - Include specifics from chunks (instrument details, conditions)
  - 4-10 techniques for a typical experimental paper

================================================================================
MINIMUM CONTENT GUIDELINES:
================================================================================
For a typical research article, aim for AT LEAST:
  - 5 key_findings (more for comprehensive papers)
  - 8 quantitative_results (more for data-heavy papers)  
  - 4 citable_claims
  - 4 techniques_used

If the chunks don't contain enough data for these minimums, extract what's available.
Do NOT fabricate to meet minimums - use what's in the chunks.

================================================================================
RULES:
================================================================================
- Output valid JSON only - no markdown, no code blocks, no preamble
- Use null for genuinely unavailable information
- Use empty array [] for list fields with no data
- NEVER fabricate - only include information from the chunks
- Preserve specific numbers exactly as extracted
- When chunks disagree, prefer the more detailed/specific version
{corrections_section}
JSON:'''


# =============================================================================
# Legacy Deep Tier Prompt (kept for reference - use CHUNK + CONSOLIDATION instead)
# =============================================================================

_LEGACY_DEEP_EXTRACTION_PROMPT = '''You are a scientific literature analyst performing detailed extraction for citation matching and research discovery.

This is a DEEP extraction from full paper text. A quick extraction was already performed from the abstract.
Your extraction will be compared against the quick extraction for consistency verification.

PAPER TITLE: {title}

JOURNAL: {journal}

AUTHORS: {authors}

YEAR: {year}

ABSTRACT: {abstract}

{full_text_section}

Extract ALL fields below in JSON format. Be thorough and specific:

{{
    "paper_type": "<type>",
    "topics": ["<topic1>", "<topic2>", "<topic3>", ...],
    "one_sentence_summary": "<comprehensive summary>",
    "key_findings": ["<finding1>", "<finding2>", ...],
    "methodology_summary": "<methodology description>",
    "quantitative_results": [
        {{"metric": "<name>", "value": "<number>", "unit": "<unit>", "conditions": "<context>"}}
    ],
    "citable_claims": ["<claim1>", "<claim2>", ...],
    "techniques_used": [
        {{"technique": "<name>", "purpose": "<why used>", "specifics": "<details>"}}
    ],
    "experimental_conditions": {{
        "materials": ["<material1>", ...],
        "temperature_range": "<range>",
        "pressure": "<range>",
        "key_parameters": ["<param1>", ...]
    }},
    "discussion_summary": "<interpretation of results>",
    "research_context": {{
        "problem_addressed": "<what gap or problem>",
        "novelty": "<what is new>",
        "limitations": "<acknowledged limitations>",
        "significance": "<broader impact>"
    }},
    "prior_work_comparison": [
        {{"reference_claim": "<what others did>", "this_work": "<what this paper did>", "improvement": "<quantified if possible>"}}
    ],
    "citation_contexts": {{
        "introduction": "<why cite in intro>",
        "methods": "<why cite in methods>",
        "results": "<why cite for comparison>",
        "discussion": "<why cite in discussion>"
    }},
    "future_directions": ["<direction1>", "<direction2>", ...],
    "papers_to_follow": [
        {{"title_fragment": "<partial title or description>", "reason": "<why important to read>"}}
    ]
}}

================================================================================
FIELDS 1-3: CORE METADATA (also in quick extraction - verify consistency)
================================================================================

FIELD 1: paper_type
Select ONE type based on FULL CONTENT. Use journal name as hint but prioritize content.

"research_article" - Original research (most common, ~70%):
  - Has hypothesis, methods, new data/results
  - Journals: Nature, Science, JACS, ACS Nano, Advanced Materials, etc.

"review" - Survey of existing literature:
  - Summarizes multiple studies, no new experimental data
  - Look for: "review", "survey", "overview", "state-of-the-art", "recent advances"
  - Journals: Chemical Reviews, Nature Reviews, Annual Review of..., Progress in...

"perspective" - Opinion/commentary piece:
  - Author viewpoint, shorter, less structured than reviews
  - Look for: "perspective", "opinion", "commentary", "viewpoint", "outlook"

"letter" - Short/rapid communication:
  - Brief format, preliminary or urgent results
  - Look for: "letter", "communication", "brief report", "rapid"
  - Journals: Applied Physics Letters, Nano Letters, ...Letters

"conference" - Conference proceedings:
  - Look for: "proceedings", "conference", symposium references
  - Journals: Proc. SPIE, IEEE proceedings, MRS Advances

"thesis" - Dissertation or thesis chapter
"book_chapter" - Chapter from edited book
"patent" - Patent document
"other" - Only if none above fit

---

FIELD 2: topics
Array of 3-5 topics as NOUN PHRASES, ordered from broad to specific.

HIERARCHY:
1. Research field (broad): "materials science", "surface chemistry", "nanofabrication"
2. Subfield: "thin film deposition", "photolithography", "surface analysis"
3. Technique/method: "atomic layer deposition", "EUV lithography", "XPS"
4. Materials/systems: "aluminum oxide", "photoresist", "high-k dielectrics"
5. Application (if clear): "semiconductor manufacturing", "flexible electronics"

FORMAT RULES:
- Use lowercase unless proper noun
- Noun phrases only ("film growth" not "growing films")
- Be specific: "X-ray photoelectron spectroscopy" not "surface analysis"

DOMAIN EXAMPLES:
- Materials/Thin Films: "atomic layer deposition" → "plasma-enhanced ALD" → "Al2O3" → "high-k dielectrics"
- Lithography: "lithography" → "EUV lithography" → "photoresist" → "chemically amplified resists"
- Characterization: "X-ray photoelectron spectroscopy" → "XPS peak fitting" → "binding energies"
- Surface Science: "surface chemistry" → "adsorption mechanisms" → "ligand exchange"

BAD EXAMPLES (avoid): "study", "analysis", "novel method", "high performance"

---

FIELD 3: one_sentence_summary
One sentence (20-40 words) capturing the paper's main contribution.

FORMAT BY PAPER TYPE:
- research_article: "[Method] was used to [study] [system], [achieving] [key result]."
- review: "This review [surveys] [topic], covering [scope] and [identifying] [insight]."
- perspective: "This perspective [discusses] [topic], [proposing] [viewpoint]."
- letter: "[Key finding] is demonstrated in [system] using [method]."
- Default: "This work [investigates] [topic], [contributing] [main contribution]."

AVOID: Starting with "This paper...", vague claims, multiple sentences

================================================================================
FIELDS 4-15: DEEP EXTRACTION (from full text only)
================================================================================

FIELD 4: key_findings
Array of 3-6 specific findings with quantitative data where available.
Example: [
    "Achieved growth rate of 1.2 Å/cycle at 80°C, 40% higher than thermal ALD",
    "Film density of 9.5 g/cm³ confirmed by XRR, matching bulk HfO2",
    "Breakdown field of 8 MV/cm, exceeding ITRS requirements",
    "Step coverage >95% in 50:1 aspect ratio trenches",
    "Carbon contamination below XPS detection limit (<0.5 at%)"
]

---

FIELD 5: methodology_summary
3-5 sentences covering experimental/computational setup.
Example: "HfO2 films were deposited using a custom plasma-enhanced ALD reactor with a remote ICP plasma source. The precursor TEMAH was delivered at 60°C with N2 carrier gas, followed by O2 plasma exposure (300W, 2s). Film properties were characterized by spectroscopic ellipsometry (thickness), XRR (density), XPS (composition), and electrical measurements on MOS capacitors."

---

FIELD 6: quantitative_results
Array of ALL numerical results with proper context. CRITICAL for citation matching.
Example: [
    {{"metric": "growth rate", "value": "1.2", "unit": "Å/cycle", "conditions": "80°C, 300W plasma"}},
    {{"metric": "film density", "value": "9.5", "unit": "g/cm³", "conditions": "as-deposited"}},
    {{"metric": "refractive index", "value": "2.08", "unit": "", "conditions": "at 632 nm"}},
    {{"metric": "breakdown field", "value": "8", "unit": "MV/cm", "conditions": "50nm film on Si"}}
]

---

FIELD 7: citable_claims
Specific, quotable assertions that could support a citation.
Example: [
    "Plasma-enhanced ALD enables high-quality HfO2 deposition below 100°C",
    "Remote plasma configuration prevents ion bombardment damage to growing film",
    "TEMAH precursor provides superior film purity compared to HfCl4"
]

---

FIELD 8: techniques_used
Characterization and fabrication methods with specifics.
Example: [
    {{"technique": "plasma-enhanced ALD", "purpose": "low-temperature film growth", "specifics": "TEMAH/O2 plasma, 80°C"}},
    {{"technique": "XPS", "purpose": "composition analysis", "specifics": "Hf 4f and O 1s peaks, Ar+ sputtering for depth profile"}},
    {{"technique": "spectroscopic ellipsometry", "purpose": "thickness measurement", "specifics": "Cauchy model, 300-800nm range"}}
]

---

FIELD 9: experimental_conditions
Key experimental parameters.
Example: {{
    "materials": ["HfO2", "TEMAH precursor", "Si(100) substrate", "TiN electrode"],
    "temperature_range": "60-150°C",
    "pressure": "1-3 Torr",
    "key_parameters": ["plasma power (100-500W)", "pulse time (0.5-2s)", "purge time (5-15s)"]
}}

---

FIELD 10: discussion_summary
Authors' interpretation of results, 2-4 sentences.
Example: "The enhanced growth rate at low temperature is attributed to the higher reactivity of oxygen radicals compared to H2O. The authors propose that remote plasma geometry is critical for preventing ion damage while maintaining sufficient radical flux. Comparison with thermal ALD shows that plasma activation compensates for reduced thermal energy."

---

FIELD 11: research_context
Scientific positioning of the work.
Example: {{
    "problem_addressed": "Conventional thermal ALD of HfO2 requires >250°C, incompatible with temperature-sensitive substrates",
    "novelty": "First demonstration of PE-ALD HfO2 below 100°C with electrical properties meeting device requirements",
    "limitations": "Limited to blanket films; pattern loading effects not studied",
    "significance": "Enables high-k integration on flexible electronics and back-end-of-line applications"
}}

---

FIELD 12: prior_work_comparison
How this work advances the field compared to prior work.
Example: [
    {{"reference_claim": "Previous PE-ALD HfO2 required >150°C", "this_work": "Achieved quality films at 80°C", "improvement": "70°C reduction in process temperature"}},
    {{"reference_claim": "Prior low-T films had high carbon content", "this_work": "Carbon below detection limit", "improvement": ">10x purity improvement"}}
]

---

FIELD 13: citation_contexts
Why someone would cite this paper in different manuscript sections.
Example: {{
    "introduction": "Cite as key advance in low-temperature ALD, enabling new applications",
    "methods": "Cite for PE-ALD recipe and optimal plasma parameters",
    "results": "Cite for comparison of growth rates and film properties",
    "discussion": "Cite for plasma-surface reaction mechanism"
}}

---

FIELD 14: future_directions
Suggested follow-up research mentioned by authors.
Example: [
    "Investigate pattern loading effects in high aspect ratio structures",
    "Extend approach to other high-k materials (ZrO2, Al2O3)",
    "Study long-term reliability under electrical stress"
]

---

FIELD 15: papers_to_follow
Key references from the paper's bibliography worth reading (2-4 papers).
Example: [
    {{"title_fragment": "Puurunen 2005 surface chemistry review", "reason": "Foundational ALD mechanism reference"}},
    {{"title_fragment": "Kim 2019 low-temperature plasma ALD", "reason": "Direct comparison study"}}
]

================================================================================
RULES (must follow)
================================================================================
- Output valid JSON only - no markdown, no code blocks, no explanation
- Use only the paper_type values listed above (use "other" only if truly none fit)
- topics must be an array with 3-5 items
- one_sentence_summary must be a single sentence
- Use null for fields where information is genuinely unavailable
- Use empty array [] for list fields with no data (not null)
- Do NOT fabricate information not present in the paper

================================================================================
GUIDELINES (best practices)
================================================================================
- Include specific numbers, percentages, temperatures, dimensions where available
- quantitative_results should capture ALL numerical results - critical for citation matching
- key_findings and citable_claims must be concrete assertions with evidence, not vague statements
- For methodology/techniques, be specific (e.g., "XPS with Al Kα source" not just "spectroscopy")
- papers_to_follow should identify 2-4 key references from bibliography worth reading
- Use established scientific terminology

================================================================================
VERIFICATION NOTE
================================================================================
Fields 1-3 (paper_type, topics, one_sentence_summary) were already extracted from the abstract.
Your deep extraction should be CONSISTENT with the quick extraction, though may be refined:
- paper_type: Should match unless full text reveals different content type
- topics: May add 1-2 more specific topics found in full text
- one_sentence_summary: May include more specific quantitative results from full text

If you find significant inconsistency (e.g., abstract said "review" but paper is clearly research),
note this is acceptable - the full text provides more accurate information.

================================================================================
FINAL CHECK
================================================================================
Before outputting, verify:
- paper_type matches the actual full content
- All topics are discussed in the paper
- Summary accurately reflects the paper's main contribution
- key_findings contain specific, verifiable claims from the paper
- quantitative_results have correct units and conditions
- No information was fabricated or hallucinated

JSON:'''


# =============================================================================
# Prompt Generation Functions
# =============================================================================

def get_extraction_prompt(
    title: str,
    abstract: str,
    full_text: Optional[str] = None,
    tier: Literal["quick", "deep"] = "deep",
    authors: Optional[str] = None,
    year: Optional[int] = None,
    journal: Optional[str] = None,
    max_chars: int = 60000,
) -> str:
    """Generate extraction prompt for the specified tier.

    Args:
        title: Paper title
        abstract: Paper abstract
        full_text: Full paper text (only used for deep tier)
        tier: "quick" (abstract only) or "deep" (full text)
        authors: Author names (for deep tier)
        year: Publication year (for deep tier)
        journal: Journal name (helps infer paper_type)
        max_chars: Maximum characters for full text (deep tier)

    Returns:
        Formatted prompt string ready for LLM
    """
    if tier == "quick":
        return QUICK_EXTRACTION_PROMPT.format(
            title=title,
            journal=journal or "Not specified",
            abstract=abstract or "Not available",
        )

    # Deep tier
    full_text_section = ""
    if full_text:
        # Truncate if needed
        if len(full_text) > max_chars:
            # Smart truncation - keep beginning and end
            half = max_chars // 2
            full_text_section = (
                f"FULL TEXT ({len(full_text):,} chars, truncated to {max_chars:,}):\n"
                f"{full_text[:half]}\n\n"
                f"[... middle section truncated ...]\n\n"
                f"{full_text[-half:]}"
            )
        else:
            full_text_section = f"FULL TEXT ({len(full_text):,} chars):\n{full_text}"

    return _LEGACY_DEEP_EXTRACTION_PROMPT.format(
        title=title,
        journal=journal or "Not specified",
        authors=authors or "Not specified",
        year=year or "Not specified",
        abstract=abstract or "Not available",
        full_text_section=full_text_section,
    )


def get_chunk_extraction_prompt(
    title: str,
    chunk_text: str,
    chunk_number: int,
    total_chunks: int,
    prior_context: str = "",
) -> str:
    """Generate prompt for extracting information from a single paper chunk.

    Used in the first pass of deep extraction, processing each chunk separately.

    Args:
        title: Paper title
        chunk_text: Text content of this chunk
        chunk_number: 1-indexed chunk number
        total_chunks: Total number of chunks in the paper
        prior_context: Facts-only context accumulated from earlier chunks
            (e.g., glossary of defined terms, sections seen so far).
            Empty string when there is no prior context.

    Returns:
        Formatted prompt string for chunk extraction
    """
    return CHUNK_EXTRACTION_PROMPT.format(
        title=title,
        chunk_text=chunk_text,
        chunk_number=chunk_number,
        total_chunks=total_chunks,
        prior_context=prior_context,
    )


def get_consolidation_prompt(
    title: str,
    abstract: str,
    quick_extraction: dict,
    chunk_extractions: list[dict],
    journal: Optional[str] = None,
    authors: Optional[str] = None,
    year: Optional[int] = None,
    corrections: Optional[str] = None,
) -> str:
    """Generate prompt for consolidating chunk extractions into final schema.

    Used in the second pass of deep extraction, synthesizing all chunk data.

    Args:
        title: Paper title
        abstract: Paper abstract
        quick_extraction: Dict from quick extraction (for verification)
        chunk_extractions: List of dicts from chunk extraction pass
        journal: Journal name
        authors: Author names
        year: Publication year
        corrections: Optional feedback from a previous failed verification
            attempt. When provided, a CORRECTIONS section listing the issues
            is appended to the prompt so the model can fix them.

    Returns:
        Formatted prompt string for consolidation
    """
    import json

    # Format quick extraction as readable JSON
    quick_json = json.dumps(quick_extraction, indent=2) if quick_extraction else "{}"

    # Format chunk extractions with chunk numbers
    chunk_sections = []
    for i, chunk_data in enumerate(chunk_extractions, 1):
        chunk_json = json.dumps(chunk_data, indent=2)
        chunk_sections.append(f"Chunk {i}:\n{chunk_json}")
    chunks_json = "\n\n".join(chunk_sections) if chunk_sections else "No chunk extractions available"

    corrections_section = ""
    if corrections:
        corrections_section = (
            "\nCORRECTIONS - a previous attempt failed verification. Fix these issues; "
            "only report values you can support with a verbatim quote:\n" + corrections + "\n"
        )

    return CONSOLIDATION_PROMPT.format(
        title=title,
        journal=journal or "Not specified",
        authors=authors or "Not specified",
        year=year or "Not specified",
        abstract=abstract or "Not available",
        quick_extraction=quick_json,
        chunk_extractions=chunks_json,
        corrections_section=corrections_section,
    )


def get_schema_for_tier(tier: Literal["quick", "deep"]) -> dict:
    """Get the extraction schema for a tier.

    Returns dict with required/optional field lists for validation.
    """
    return EXTRACTION_SCHEMA.get(tier, EXTRACTION_SCHEMA["deep"])


# =============================================================================
# Response Parsing
# =============================================================================

def parse_extraction_response(response_text: str) -> dict:
    """Parse JSON extraction response from LLM.

    Handles common LLM response quirks:
    - Markdown code blocks
    - Preamble text before JSON
    - Trailing text after JSON

    Args:
        response_text: Raw LLM response

    Returns:
        Parsed dict or empty dict on failure
    """
    import json
    import re

    text = response_text.strip()

    # Remove markdown code blocks
    if text.startswith("```"):
        # Find the end of the code block
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]  # Remove opening ```json or ```
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]  # Remove closing ```
        text = "\n".join(lines)

    # Try to find JSON object
    # Look for first { and last }
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        return {}

    json_str = text[start:end + 1]

    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        # Try to fix common issues
        # Remove trailing commas before } or ]
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            return {}


def validate_extraction(data: dict, tier: Literal["quick", "deep"]) -> tuple[bool, list[str]]:
    """Validate extraction against schema.

    Args:
        data: Parsed extraction dict
        tier: Extraction tier

    Returns:
        (is_valid, list of missing required fields)
    """
    schema = EXTRACTION_SCHEMA.get(tier, EXTRACTION_SCHEMA["deep"])
    required = schema["required"]

    missing = [field for field in required if field not in data or data[field] is None]

    return len(missing) == 0, missing
