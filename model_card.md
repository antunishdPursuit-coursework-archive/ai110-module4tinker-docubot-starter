# DocuBot Model Card

## 1. System overview

DocuBot answers developer questions from the four Markdown files in `docs/`.
Those files describe a fictional application; this repository does not require
running that application's server or database. The input is a question and a
local documentation folder. Outputs are raw source sections, a grounded Gemini
answer, or an explicit refusal when evidence is missing.

The three modes deliberately separate retrieval from generation:

- **Naive generation:** the existing `naive_answer_over_full_docs()` helper
  ignores its `all_text` argument and sends only the developer question.
  It cannot know this project's private documentation.
- **Retrieval only:** local index/ranking returns source sections and filenames;
  no API request is made.
- **RAG:** retrieval selects evidence, then Gemini receives those sections and
  must answer only from them, cite files, or refuse. No retrieved evidence
  means refusal before generation.

## 2. Retrieval design and tradeoffs

`docubot.py` loads four files and builds an inverted index from normalized
keywords to filenames. Tokens split punctuation, identifiers, and routes.
Simple plurals and a small generate/connect word-form map reduce exact-word
mismatches; common filler words are excluded.

The 36 Markdown sections retain parent headings and fenced examples. Query
keywords select candidate files through the index. A section's score is the
number of distinct query keywords found in its filename plus text. Repeating a
word does not increase that score. Ties use heading overlap, then shorter text,
then deterministic filename/text ordering.

To qualify, a section must match at least half the distinct query keywords and
at least two keywords, unless the query has one keyword or names the source
file. `top_k` defaults to three. Empty/stop-word-only queries, nonpositive top-k,
and no qualifying evidence return no snippets. Both answer modes then say:

> I do not know based on these docs.

This is a readable lexical heuristic, not a calibrated confidence score or a
semantic relevance guarantee. It reduces weak incidental matches, but can miss
synonyms and can still return extra sections with shared terms.

## 3. Gemini behavior

The configured model is `gemini-3.1-flash-lite`. An ignored local `.env` or shell
variable supplies `GEMINI_API_KEY`; keys are not part of this repository.
The RAG prompt requires source-only answers and file references. When snippets
are insufficient, it requests this exact response:

> I do not know based on the docs I have.

A grounding instruction does not prove factual correctness. Returned claims
must still be compared with the cited sections. Provider errors are reported
as errors, not treated as answers or scored as successful generation.

## 4. October 24, 2026 verification

Environment: Python 3.13.17, project-local `.venv`, existing requirements
`google-genai` 2.33.0 and `python-dotenv` 1.2.4. No dependencies were added to
`requirements.txt`. Run from the repository root:

```powershell
.\.venv\Scripts\python.exe -B evaluation.py
.\.venv\Scripts\python.exe -B main.py
```

The unchanged eight-query evaluation prints **0.88 (7/8)** before and after
section retrieval. It measures whether any top-three filename matches an
expected source, not answer accuracy or snippet precision. Its unsupported
payment question has no expected file and always counts as a miss, including
when refusal is correct. The unchanged overall number therefore hides this
important improvement.

| Identical question selected for comparison | Fresh retrieval-only observation | Fresh naive / RAG observation |
| --- | --- | --- |
| Where is the auth token generated? | First result is AUTH.md / Token Generation, 466 characters instead of the 2,305-character full file; contains generate_access_token, auth_utils.py, and AUTH_SECRET_KEY. | First naive API request failed with 401; no fresh successful naive or generated RAG answer. |
| How do I connect to the database? | DATABASE.md / Connection Configuration is first and includes DATABASE_URL and the documented connection examples. | Not called after the credential failure. |
| Which endpoint lists all users? | API_REFERENCE.md / GET /api/users is first; includes the admin-only restriction. | Not called after the credential failure. |
| Is there any mention of payment processing in these docs? | No snippets; explicit refusal. The old whole-file retriever returned an irrelevant SETUP.md. | RAG refusal before any API request verified offline; naive comparison remains blocked. |
| How can I prolong my session? | No snippets; the retriever does not connect this paraphrase to token refresh. | RAG also refuses before generation: a concrete retrieval-limited failure for a human-interpretable refresh question. Naive comparison remains blocked. |

Temporary in-memory checks covered first-result source/content, shorter
snippets, unsupported/empty/stop-word-only queries, zero/negative top-k,
Markdown fences, and no LLM request on unsupported evidence. Python syntax and
interactive mode-2 supported/refusal paths passed. Existing `evaluation.py`
was kept unchanged. No test files were added or removed.

### Live comparison blocker

One naive request was attempted with the existing key. Gemini returned:

```text
401 UNAUTHENTICATED
ACCOUNT_STATE_INVALID
The bound service account is deleted or disabled.
The service account bound to the API key must be active.
```

The experiment stopped immediately; no repeated requests or model switching
were attempted. This is an authentication failure, not an observed
hallucination or a model-quality result. Part 1's fresh naive observation and
Part 4's full same-question three-mode comparison are incomplete until an
active key allows those modes to run. Three-mode evaluation is not complete.

### Historical observations, separate from this run

The earlier model card reported RAG answers naming `generate_access_token`
in `auth_utils.py`, DATABASE_URL/SQLite/PostgreSQL setup, GET /api/users, and
/api/refresh, plus refusal on payment processing. Those are prior recorded
observations, not fresh successful API results on October 24. Its naive-mode
column was not evaluated. Earlier model-configuration notes:

The LLM-based modes needed a few model attempts before they worked. `gemini-2.5-flash` and `gemma-3-27b-it` did not work correctly during testing, so I first focused on retrieval-only behavior because it does not depend on the model API. After switching to `gemini-3.1-flash-lite`, the RAG mode worked and could answer supported questions with file references while refusing unsupported questions.

## 5. Failure cases and guardrails

1. **Weak incidental match (baseline, corrected):** the payment-processing
   question previously returned all of SETUP.md at score 1. It now has no
   qualifying section and refuses in retrieval and RAG before an API call.
2. **Overly broad output (baseline, reduced):** the auth question returned
   full AUTH.md/API_REFERENCE.md text. The relevant token-generation section
   is now first; up to three sections can still contain less useful context.
3. **False refusal (current limitation):** `How can I prolong my session?`
   retrieves nothing, even though a person could direct the user to token
   refresh. RAG cannot recover evidence that retrieval never supplies.
4. **Provider availability (current blocker):** the saved key cannot
   authenticate. Mode 2 still works offline; this does not make modes 1/3
   verified or justify substituting remembered results.

The retrieval threshold and the RAG evidence/refusal prompt are complementary
guardrails. Neither is an authorization control or protection against all
prompt injection. Only the selected docs are sent in RAG mode; do not place
secrets or unapproved private material in the corpus.

## 6. Interpretation and responsible use

The intended comparison is fluency versus grounding: naive generation can
sound helpful without project evidence; raw retrieval is inspectable but less
readable; RAG can summarize evidence clearly, while still inheriting retrieval
errors. These are design expectations. The current API failure prevents fresh
claims about which naive answer was fluent/wrong or which generated RAG answer
was clearer in this run.

Use DocuBot as a documentation navigation aid. Check cited files before
changing authentication, database configuration, or API behavior. Stop when
there is no evidence, distinguish provider failure from refusal, and never
interpret the 0.88 filename hit rate as 88% correct answers. Future work could
improve synonym coverage, assess sentence-level support and precision, and
challenge shared-word false positives. None of that is claimed implemented.
