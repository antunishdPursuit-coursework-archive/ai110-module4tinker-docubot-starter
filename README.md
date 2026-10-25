# DocuBot

DocuBot is a small documentation assistant that helps answer developer questions about a codebase.  
It can operate in three different modes:

1. **Naive LLM mode**  
   Asks Gemini the question without sending project documentation. The inherited helper name mentions full docs, but its prompt intentionally ignores them to expose ungrounded guesses.

2. **Retrieval only mode**  
   Uses a simple indexing and scoring system to retrieve relevant snippets without calling an LLM.

3. **RAG mode (Retrieval Augmented Generation)**  
   Retrieves relevant snippets, then asks Gemini to answer using only those snippets.

The docs folder contains realistic developer documents (API reference, authentication notes, database notes), but these files are **just text**. They support retrieval experiments and do not require students to set up any backend systems.

---

## Setup

### 1. Install Python dependencies

    pip install -r requirements.txt

### 2. Configure environment variables

Copy the example file:

    cp .env.example .env

Then edit `.env` to include your Gemini API key:

    GEMINI_API_KEY=your_api_key_here

If you do not set a Gemini key, you can still run retrieval only mode.

---

## Running DocuBot

Start the program:

    python main.py

Choose a mode:

- **1**: Naive LLM (no project documentation)
- **2**: Retrieval only (no LLM)  
- **3**: RAG (retrieval + Gemini)

You can use built in sample queries or type your own.

---

## Running Retrieval Evaluation (optional)

    python evaluation.py

This prints simple retrieval hit rates for sample queries.

---

## Modifying the Project

You will primarily work in:

- `docubot.py`  
  Implement or improve the retrieval index, scoring, and snippet selection.

- `llm_client.py`  
  Adjust the prompts and behavior of LLM responses.

- `dataset.py`  
  Add or change sample queries for testing.

---

## Requirements

- Python 3.9+
- A Gemini API key for LLM features (only needed for modes 1 and 3)
- No database, no server setup, no external services besides LLM calls

## Focused retrieval and refusal (Part 3)

`docubot.py` indexes the original files and splits Markdown into sections,
keeping parent headings and fenced examples together. Query keywords narrow the candidate files. An explicit `AUTH.md` or `.txt`
reference restricts the sources; the filename and extension are removed from
the question before scoring. Only section text provides evidence. Tokens split
routes/identifiers, normalize simple plurals, and map a few generate/connect
word forms. Sections rank by distinct keyword matches, then heading
matches and shorter sections. Repeating a word does not increase the score.

A section must cover at least half the content query keywords and match at
least two, unless the content question contains only one keyword. Naming a
file does not waive that condition: `AUTH.md payments` refuses, while
`Where is the auth token generated in AUTH.md?` retrieves the auth evidence.
No qualifying section means `I do not know based on these docs.` in retrieval
and RAG modes, before an LLM request. This threshold is a heuristic, not a
probability: synonyms can cause false refusals and shared words can still
retrieve the wrong section. The RAG prompt separately requires evidence and
file references. Verify claims against the cited source.

Try `Where is the auth token generated?` and then
`Is there any mention of payment processing in these docs?` in mode 2.
The first returns focused authentication evidence; the second refuses.
The optional existing `evaluation.py` measures expected-file hits, not answer
accuracy. Its unsupported query has no expected file and always counts as a
miss, even when refusal is correct.

## Three-mode comparison (Parts 1 and 4)

The October 24, 2026 run used identical questions in all three modes with
`gemini-3.1-flash-lite`. See [the model card](model_card.md) for the five-query
matrix, actual RAG excerpts, the naive `/users` versus documented `/api/users`
difference, the missed session paraphrase, and the omitted admin-only qualifier.
The earlier key failure was resolved before recording these live results.

To repeat, run `python main.py`, choose 1, 2, then 3, and enter the same question
each time. Include a supported question and the unsupported payment question.
Retrieval is local; modes 1 and 3 need an active Gemini key. No-evidence RAG
questions refuse before making an API request. Verify answers against source
sections rather than assuming that a fluent answer or file citation is enough.
