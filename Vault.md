# Semantic Croissant Vault

The **Vault** is the central storage and provenance-tracking system in the Semantic Croissant ecosystem. It stores unstructured data (Markdown documents, extracted text, agent analysis) alongside highly structured, schema-compliant Croissant JSON-LD metadata. 

It is backed by **MinIO** (object storage) and **Elasticsearch** (for full-text indexing), with metadata synced to the **QLever** knowledge graph.

## Core Concepts

1. **Dual-File Structure**: Every dataset in the Vault consists of two files:
   - `{hash}.md` (or `.gz`, `.csv`): The actual content, research notes, or extracted text.
   - `{hash}.jsonld`: The Croissant JSON-LD metadata describing the content, creators, and provenance.
2. **UNF-6 Fingerprinting**: Content is hashed using the UNF-6 algorithm (Universal Numeric Fingerprint) upon creation. This prevents duplication and provides a unique, verifiable identifier.
3. **Decentralized Identifiers (DIDs)**: Agents and human users are identified using DIDs. When a document is saved to the Vault, the system embeds the creator's DID and a digital signature in the JSON-LD to ensure trust and attribution.
4. **Session Chains**: Interactions within a specific context are grouped using a `session_id`. This creates a traceable lineage of thought and data derivation.

## MCP Tools for Vault Operations

The MCP Server exposes several tools to interact with the Vault:

- `save_to_vault`: Saves new content to the Vault. **Agents must automatically generate the accompanying Croissant JSON-LD**.
- `read_vault_article`: Retrieves a Vault document by its ID, filename, or URL. Automatically appends a `session_id` instruction if the document belongs to an ongoing session.
- `list_vault_documents`: Lists documents currently stored in the Vault bucket.
- `verify_document_provenance`: Verifies the DID signatures, UNF hashes, and lists all creators associated with a document.
- `update_vault_document`: Used for versioning, collaborative updates, and establishing complex provenance (see details below).

---

## The `update_vault_document` Workflow (Document A & Document B)

The `update_vault_document` tool is designed for scenarios where an AI agent or user creates a derivative analysis (Document B) based on an existing source document (Document A). 

### How it Works

When an agent calls `update_vault_document(target_id="DocA", new_content="Analysis", referenced_ids=["DocB"])`:

1. **Document A (The Original Source)**:
   - The tool fetches the existing `{DocA}.md` and `{DocA}.jsonld` from the Vault.
   - If Elasticsearch has more recent metadata for Document A, it merges it.

2. **Document B (The New Derivative Analysis)**:
   - If `new_content` is provided, the tool generates a new unique ID (e.g., `TaskID`) and saves the content as a new file (`{TaskID}.md`).
   - It automatically generates a basic JSON-LD for Document B (`{TaskID}.jsonld`), explicitly setting its `isBasedOn` property to point back to Document A.
   - The tool then **injects a Markdown link** to Document B at the bottom of Document A under a `### Related AI Analysis` section.

3. **Cross-Referencing (`referenced_ids`)**:
   - The tool takes the newly created `TaskID` (Document B) and any other IDs provided in `referenced_ids`.
   - It updates Document A's JSON-LD by adding these referenced IDs to Document A's `isBasedOn` array, effectively establishing a two-way provenance link.
   - The creators of the referenced documents are fetched and preserved in the new metadata.

4. **Persistence**:
   - Document A's updated Markdown and JSON-LD are re-uploaded to MinIO, overwriting the old versions.
   - The Elasticsearch index is updated to reflect the new references and appended Markdown links.

### Summary of the Relationship

- **Document B** is saved as a distinct entity in the Vault.
- **Document B** acknowledges its source by pointing to **Document A** in its JSON-LD (`isBasedOn`).
- **Document A** acts as a living document; its Markdown is updated with a hyperlink to the new **Document B**, and its JSON-LD schema is expanded to include **Document B** in its provenance graph.
