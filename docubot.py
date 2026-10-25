"""
Core DocuBot class responsible for:
- Loading documents from the docs/ folder
- Building a simple retrieval index (Phase 1)
- Retrieving relevant snippets (Phase 1)
- Supporting retrieval only answers
- Supporting RAG answers when paired with Gemini (Phase 2)
"""

import os
import glob
import re

class DocuBot:
    STOP_WORDS = {
        "a", "an", "and", "any", "are", "by", "does", "do", "for", "from",
        "how", "i", "in", "is", "it", "of", "on", "or", "the", "there",
        "these", "this", "to", "what", "when", "where", "which", "with",
        "all", "can", "client", "could", "doc", "docs", "documentation",
        "me", "mention", "my", "please", "some", "tell", "you",
    }

    def __init__(self, docs_folder="docs", llm_client=None):
        """
        docs_folder: directory containing project documentation files
        llm_client: optional Gemini client for LLM based answers
        """
        self.docs_folder = docs_folder
        self.llm_client = llm_client

        # Load documents into memory
        self.documents = self.load_documents()  # List of (filename, text)

        # Build a retrieval index (implemented in Phase 1)
        self.index = self.build_index(self.documents)
        self.sections = [
            (filename, section)
            for filename, text in self.documents
            for section in self.split_sections(text)
        ]

    # -----------------------------------------------------------
    # Document Loading
    # -----------------------------------------------------------

    def load_documents(self):
        """
        Loads all .md and .txt files inside docs_folder.
        Returns a list of tuples: (filename, text)
        """
        docs = []
        pattern = os.path.join(self.docs_folder, "*.*")
        for path in glob.glob(pattern):
            if path.endswith(".md") or path.endswith(".txt"):
                with open(path, "r", encoding="utf8") as f:
                    text = f.read()
                filename = os.path.basename(path)
                docs.append((filename, text))
        return docs

    # -----------------------------------------------------------
    # Index Construction (Phase 1)
    # -----------------------------------------------------------

    WORD_FORMS = {
        "generated": "generate", "generation": "generate", "generating": "generate",
        "connection": "connect", "connecting": "connect", "connected": "connect",
    }

    def clean_word(self, word):
        """Normalize punctuation and simple plurals without semantic search."""
        word = word.lower().strip(".,:;!?`\"'()[]{}")
        if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]
        return self.WORD_FORMS.get(word, word)

    def get_keywords(self, text):
        """Split identifiers/routes too, so AUTH_SECRET_KEY includes auth."""
        words = [self.clean_word(word) for word in re.findall(r"[a-z0-9]+", text.lower())]
        return [word for word in words if word and word not in self.STOP_WORDS]

    def split_sections(self, text):
        """Keep Markdown sections with their parent headings for context."""
        sections = []
        headings = []
        body = []
        in_fence = False

        def save_section():
            if any(line.strip() for line in body):
                sections.append("\n".join(headings + body).strip())

        for line in text.splitlines():
            if line.lstrip().startswith("```"):
                in_fence = not in_fence
            heading = re.match(r"^(#{1,6})\s+", line) if not in_fence else None
            if heading:
                save_section()
                level = len(heading.group(1))
                headings = [h for h in headings if len(h.split()[0]) < level]
                headings.append(line)
                body = []
            else:
                body.append(line)
        save_section()
        return sections

    def build_index(self, documents):
        """
        Build a tiny inverted index mapping lowercase words to the documents
        they appear in.

        Example structure:
        {
            "token": ["AUTH.md", "API_REFERENCE.md"],
            "database": ["DATABASE.md"]
        }

        Keep this simple: split on whitespace, lowercase tokens,
        ignore punctuation if needed.
        """
        index = {}

        for filename, text in documents:
            for cleaned_word in self.get_keywords(text):
                if cleaned_word not in index:
                    index[cleaned_word] = []

                # A list is simple for this small lab; a larger system would use a set here.
                if filename not in index[cleaned_word]:
                    index[cleaned_word].append(filename)

        return index

    # -----------------------------------------------------------
    # Scoring and Retrieval (Phase 1)
    # -----------------------------------------------------------

    def score_document(self, query, text):
        """Count distinct query keywords present; repetition adds no evidence."""
        return len(set(self.get_keywords(query)) & set(self.get_keywords(text)))

    def retrieve(self, query, top_k=3):
        """Rank focused sections and decline weak keyword overlap.

        Filenames constrain sources but never count as answer evidence.
        A section needs at least half the content query's distinct keywords,
        plus two matches unless the content query has only one keyword.
        This is a small lexical heuristic, not a confidence probability.
        """
        file_pattern = r"\b[\w.-]+\.(?:md|txt)\b"
        named_files = {name.lower() for name in re.findall(file_pattern, query, re.IGNORECASE)}
        content_query = re.sub(file_pattern, " ", query, flags=re.IGNORECASE)
        query_words = set(self.get_keywords(content_query))
        if not query_words or top_k <= 0:
            return []

        candidates = set()
        for word in query_words:
            candidates.update(self.index.get(word, []))
        results = []
        for filename, section in self.sections:
            if filename not in candidates or (named_files and filename.lower() not in named_files):
                continue
            score = self.score_document(content_query, section)
            coverage = score / len(query_words)
            if coverage >= 0.5 and score >= min(2, len(query_words)):
                headings = "\n".join(line for line in section.splitlines() if line.startswith("#"))
                heading_score = self.score_document(content_query, headings)
                results.append((score, heading_score, filename, section))

        results.sort(key=lambda result: (-result[0], -result[1], len(result[3]), result[2], result[3]))
        return [(filename, section) for _, _, filename, section in results[:top_k]]

    # -----------------------------------------------------------
    # Answering Modes
    # -----------------------------------------------------------

    def answer_retrieval_only(self, query, top_k=3):
        """
        Phase 1 retrieval only mode.
        Returns raw snippets and filenames with no LLM involved.
        """
        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        formatted = []
        for filename, text in snippets:
            formatted.append(f"[{filename}]\n{text}\n")

        return "\n---\n".join(formatted)

    def answer_rag(self, query, top_k=3):
        """
        Phase 2 RAG mode.
        Uses student retrieval to select snippets, then asks Gemini
        to generate an answer using only those snippets.
        """
        if self.llm_client is None:
            raise RuntimeError(
                "RAG mode requires an LLM client. Provide a GeminiClient instance."
            )

        snippets = self.retrieve(query, top_k=top_k)

        if not snippets:
            return "I do not know based on these docs."

        return self.llm_client.answer_from_snippets(query, snippets)

    # -----------------------------------------------------------
    # Bonus Helper: concatenated docs for naive generation mode
    # -----------------------------------------------------------

    def full_corpus_text(self):
        """
        Returns all documents concatenated into a single string.
        This is used in Phase 0 for naive 'generation only' baselines.
        """
        return "\n\n".join(text for _, text in self.documents)
