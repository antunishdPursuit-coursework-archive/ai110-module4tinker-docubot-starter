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

The supplied corpus produces 36 sections. Larger sections split at paragraphs
and then word/newline boundaries, targeting 1,000 characters including repeated
parent headings. A single fenced example is kept intact even when larger than
that target. Backtick and tilde fences retain the opening marker and length;
only a matching, sufficiently long closing marker with no info text closes it.
Code text cannot change the parent heading path or contribute a heading bonus.

Query keywords select candidate files through the index. Explicit `.md`/`.txt`
references restrict those files and are removed from the content question.
A section's score counts distinct content-question keywords found in its text;
filenames and extensions provide no evidence. Repetition adds no score. Ties
use overlap in the leading heading path, then shorter text and deterministic
filename/text ordering.

To qualify, a section must match at least half the content query keywords and
at least two keywords, unless the content query contains only one keyword.
`top_k` defaults to three. Empty/stop-word-only content queries, nonpositive
top-k, unknown named sources, and no qualifying evidence return no snippets.
Both answer modes then say:

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

### Recorded same-question comparison before the retrieval refinements

Before the retrieval refinements below, all five questions ran through naive, retrieval-only, and
RAG methods with `gemini-3.1-flash-lite`. Only the key changed between the
failed and successful runs. The comparison runner loaded the current local
`.env` explicitly, allowed a 30-second timeout and one attempt per request,
and saved its responses locally. There were eight successful API requests:
five naive plus three grounded RAG. The two no-evidence RAG cases returned
locally without an API request. No model or prompt was changed for the run.

| Identical question | Naive generation | Retrieval only | RAG |
| --- | --- | --- | --- |
| Where is the auth token generated? | Asked which application/framework was in use and offered generic controller/IdP/JWT search advice. Fluent, but no project evidence. | AUTH.md / Token Generation ranked first: 466 characters rather than the 2,305-character full file; exposes the function, module, and signing variable. | Named generate_access_token in auth_utils.py and cited AUTH.md. Clearer than scanning three raw sections. |
| How do I connect to the database? | Gave generic DB_HOST/DB_PORT/.env, Node pg, SQLAlchemy, and Django examples while asking for the stack. Those examples are not this project's setup. | DATABASE.md / Connection Configuration ranked first; includes DATABASE_URL and SQLite/PostgreSQL examples. | Explained DATABASE_URL, the app.db SQLite fallback, and db.py; cited DATABASE.md. These claims appear in the retrieved sections. |
| Which endpoint lists all users? | Suggested the conventional GET /users plus /api/v1/users and other variants, while asking for the actual API. Those are not the documented route. | API_REFERENCE.md / GET /api/users ranked first and explicitly says admin-only, Authorization required, and 403 for non-admins. Also returns two less relevant sections. | Correctly named GET /api/users and cited API_REFERENCE.md, but omitted the admin-only restriction: a useful answer can still lose an important qualifier. |
| Is there any mention of payment processing in these docs? | Asked for the missing docs and offered to search payment/billing/Stripe keywords; did not establish anything about this corpus. | No snippets; explicit refusal. The old whole-file retriever returned an irrelevant SETUP.md. | Same explicit refusal, before calling Gemini. Appropriate for this unsupported topic. |
| How can I prolong my session? | Offered generic heartbeats/session-timeout/refresh advice, including /api/keep-alive and /api/refresh-token examples not in this corpus. | No snippets: this lexical retriever does not connect the paraphrase to token refresh. | Also refuses before generation. A human could point toward the documented /api/refresh workflow; RAG cannot recover evidence absent from retrieval. |

### Actual output excerpts

The following are unedited complete RAG responses from this run, not expected
answers. The users response illustrates the omitted permission qualifier.

**Where is the auth token generated?**

```text
The authentication token is generated by the `generate_access_token` function in the `auth_utils.py` module.

I relied on the file `AUTH.md` to answer this question.
```

**Which endpoint lists all users?**

```text
The endpoint to list all users is `GET /api/users`.

I relied on the file `API_REFERENCE.md`.
```

A naive excerpt for the users question was `GET /users`; the source instead
says `GET /api/users`. The naive response did acknowledge that it needed the
API name. It is generic guidance, not evidence that this codebase uses that
route. Retrieval is inspectable but verbose; RAG compresses it into readable
answers while sometimes losing details. Grounding and completeness require
separate checks.

Temporary in-memory checks covered first-result source/content, shorter
snippets, unsupported/empty/stop-word-only queries, zero/negative top-k,
Markdown fences, and no LLM request on unsupported evidence. Python syntax and
interactive mode-2 supported/refusal paths passed. Existing `evaluation.py`
was kept unchanged. No test files were added or removed.

### Offline verification of retrieval refinements

After the recorded live comparison, the retriever was refined without changing
the model, prompts, source docs, sample questions, or existing evaluation.
The retrieval and CLI checks ran offline. One supported auth question was
then checked live because the same secondary evidence sections now sort in a
different order. The generated answers in the five-query table remain
observations from the earlier run, not newly generated results.

- `AUTH.md payments`, `How does AUTH.md process payments?`, and
  `DATABASE.md payments` now return no snippets. RAG refuses them before an
  LLM request. Supported questions naming AUTH.md still retrieve its evidence.
- The heading-free 10,852-character example splits into 12 chunks, each at
  most 997 characters; `authentication token` retrieves a 50-character passage.
  Long plain lines and headed paragraphs also remain within the text target.
- Tilde and nested-backtick examples retain code headings as literal code and
  preserve the correct parent for the next section. Wrong marker types, shorter
  closers, and closing markers with trailing info text do not end a fence.
- Individual oversized fenced examples remain intact. The size target is
  deliberately a soft limit for those examples, rather than cutting code apart.
- The supplied corpus still has 36 sections; the longest is 558 characters.
  The unchanged evaluation still reports 7/8 filename hits (0.88).
- Four of the five recorded retrieval outputs are unchanged byte-for-byte.
  The auth output contains the same three sections: Token Generation stays
  first, while Environment Variables and the introduction swap positions.
  A single fresh RAG request with this context returned:

  > The auth token is generated by the `generate_access_token` function located in the `auth_utils.py` module.
  >
  > I relied on `AUTH.md` to answer this.

  This supports the current auth path; it is not a new full five-question
  generation run or a claim that the other documented RAG limits disappeared.

- Existing tests/evaluation are retained. Verification uses temporary in-memory
  probes and the CLI; no test files are added. This remains a small Markdown
  section splitter, not a complete Markdown renderer or semantic retriever.

### Earlier authentication failure, resolved

The first attempt with the previous key returned 401 UNAUTHENTICATED /
ACCOUNT_STATE_INVALID because its bound service account was deleted or
disabled. That run stopped immediately. After the local key was replaced,
the same model and methods completed the five-question comparison above.
The failed request is an authentication result, not a hallucination or an
answer-quality measurement. The current successful run supplies Parts 1 and 4
observations; the historical results below are not used as their substitute.

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
4. **Omitted qualifier (current RAG limitation):** the users response names
   GET /api/users but leaves out its admin-only restriction despite that
   evidence being retrieved. A cited answer can still be incomplete.
5. **Provider availability (observed, resolved):** the prior key could not
   authenticate. Updating the key enabled fresh modes 1/3 results; mode 2
   remained usable offline throughout.

The retrieval threshold and the RAG evidence/refusal prompt are complementary
guardrails. Neither is an authorization control or protection against all
prompt injection. Only the selected docs are sent in RAG mode; do not place
secrets or unapproved private material in the corpus.

## 6. Interpretation and responsible use

The observed comparison separates fluency, grounding, and completeness.
Naive mode was often appropriately cautious, but its polished generic examples
did not establish project facts. Raw retrieval showed the actual source at the
cost of extra reading. RAG answered the supported questions concisely with
file references, yet omitted an access restriction and inherited a false
refusal from lexical retrieval. A source citation alone is not proof that an
answer includes every relevant condition.

Use DocuBot as a documentation navigation aid. Check cited files before
changing authentication, database configuration, or API behavior. Stop when
there is no evidence, distinguish provider failure from refusal, and never
interpret the 0.88 filename hit rate as 88% correct answers. Future work could
improve synonym coverage, assess sentence-level support and precision, and
challenge shared-word false positives. None of that is claimed implemented.
