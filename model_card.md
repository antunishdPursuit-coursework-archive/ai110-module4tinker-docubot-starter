# DocuBot Model Card

## 1. System Overview

**What is DocuBot trying to do?**  
DocuBot is a small documentation assistant that answers developer questions using files in the `docs/` folder. The goal is to compare ungrounded generation with retrieval-based answers so the system can point users toward relevant documentation instead of guessing.

**What inputs does DocuBot take?**  
DocuBot takes a user question and a folder of Markdown or text documentation files. If Gemini is configured, it can also use the `GEMINI_API_KEY` environment variable for LLM-based modes.

**What outputs does DocuBot produce?**  
In retrieval-only mode, DocuBot returns the filenames and text of the most relevant retrieved documents. In RAG mode, DocuBot should use retrieved snippets to generate a grounded answer.

---

## 2. Retrieval Design

**How does your retrieval system work?**  
The system loads each Markdown or text file from `docs/`, cleans words by lowercasing them and removing surrounding punctuation, then builds an inverted index that maps keywords to filenames. Common stop words such as `the`, `is`, `what`, and `in` are skipped so the index focuses on more meaningful terms.

For scoring, DocuBot cleans the query and document text using the same keyword helper. It counts how many times each query keyword appears in a document. `retrieve()` scores every document, keeps documents with scores above zero, sorts them from highest score to lowest score, and returns the top results.

**What tradeoffs did you make?**  
This retrieval design favors simplicity and readability over advanced search quality. It is easy to understand and works well for a small documentation folder, but it does not understand synonyms, word meaning, or exact route syntax very deeply. A larger system would likely use sets, chunking, embeddings, or a more advanced ranking method.

---

## 3. Use of the LLM (Gemini)

**When does DocuBot call the LLM and when does it not?**

- Naive LLM mode: Sends the full documentation corpus to Gemini if `GEMINI_API_KEY` is configured.
- Retrieval only mode: Does not call Gemini. It only returns matching documentation snippets.
- RAG mode: Retrieves snippets first, then sends only those snippets to Gemini for a grounded answer if `GEMINI_API_KEY` is configured.

**What instructions do you give the LLM to keep it grounded?**  
The RAG prompt in `llm_client.py` instructs the model to answer only from the retrieved snippets, say when the snippets do not contain enough information, and cite the file names used. I tested RAG mode with `gemini-3.1-flash-lite`, and it answered supported questions with file references while refusing the unsupported payment-processing question.

---

## 4. Experiments and Comparisons

I ran the retrieval evaluation with:

```powershell
venv\Scripts\python.exe evaluation.py
```

The final retrieval hit rate was:

```text
Hit rate: 0.88
```

| Query | Naive LLM: helpful or harmful? | Retrieval only: helpful or harmful? | RAG: helpful or harmful? | Notes |
|------|---------------------------------|--------------------------------------|---------------------------|-------|
| Where is the auth token generated? | Not evaluated yet | Helpful | Helpful | RAG answered that `generate_access_token` in `auth_utils.py` creates the token and cited `AUTH.md`. |
| How do I connect to the database? | Not evaluated yet | Helpful | Helpful | RAG explained `DATABASE_URL`, SQLite default behavior, PostgreSQL format, and referenced `DATABASE.md` and `SETUP.md`. |
| Which endpoint lists all users? | Not evaluated yet | Helpful | Helpful | RAG answered `GET /api/users` and cited `API_REFERENCE.md`. |
| How does a client refresh an access token? | Not evaluated yet | Helpful | Helpful | RAG explained using `/api/refresh` with the Authorization header and cited `AUTH.md` and `API_REFERENCE.md`. |
| Is there any mention of payment processing in these docs? | Not evaluated yet | Harmful | Helpful | Retrieval-only returned a weak match, but RAG correctly answered: `I do not know based on the docs I have.` |

**What patterns did you notice?**  
Retrieval-only mode improved once stop words were removed from scoring. It usually finds the right document, but it may still return extra documents because the scoring method only counts keyword overlap. RAG mode produced more readable answers and handled the unsupported payment-processing question better because the prompt told the model to refuse when the snippets did not contain enough evidence.

---

## 5. Failure Cases and Guardrails

**Describe at least two concrete failure cases you observed.**

Failure case 1:

- Question: `Is there any mention of payment processing in these docs?`
- What happened: The system returned `SETUP.md`.
- What should have happened: DocuBot should have said it does not know based on the docs because payment processing is not covered.

Failure case 2:

- Question: `Which endpoint lists all users?`
- What happened: The system retrieved the correct `API_REFERENCE.md`, but it also returned unrelated files.
- What should have happened: The API reference should have been ranked clearly above unrelated documents, and weaker matches should have been filtered out.

**When should DocuBot say "I do not know based on the docs I have"?**  
DocuBot should refuse when the user asks about a topic that does not appear in the docs, such as payment processing. It should also refuse when all retrieved documents have very weak scores or only match broad generic terms.

**What guardrails did you implement?**  
The current retrieval guardrail is stop-word filtering, which reduces weak matches from common filler words. The RAG prompt also asks the model to say it does not know when the retrieved snippets do not contain enough information. A stronger future retrieval guardrail would add a minimum score threshold before returning snippets.

---

## 6. Limitations and Future Improvements

**Current limitations**

1. The retriever uses keyword counting, so it does not understand synonyms or meaning.
2. Unsupported questions can still return weak matches instead of a refusal.
3. The system returns full document text instead of smaller, more precise snippets.

**Future improvements**

1. Add a minimum score threshold so DocuBot can return "I do not know based on these docs" for weak matches.
2. Split documents into smaller sections so answers can point to more precise snippets.
3. Add automated checks for unsupported questions so retrieval-only mode can refuse weak matches before calling the LLM.

---

## 7. Responsible Use

**Where could this system cause real world harm if used carelessly?**  
DocuBot could cause harm if developers trust weak or incorrect retrieved results without checking the underlying docs. If used for security, authentication, database setup, or API behavior, a wrong answer could lead to broken integrations or unsafe implementation choices.

**What instructions would you give real developers who want to use DocuBot safely?**

- Treat DocuBot as a documentation navigation aid, not as the final source of truth.
- Always check the cited file before making production changes.
- Do not rely on answers when DocuBot returns weak or unrelated snippets.
- Add refusal thresholds before using this pattern in a real developer tool.

---
