# Asset System - Semantic Search (Conceptual)

**Status: Conceptual**
_This document outlines a proposed feature for future development. The concepts described here are for discussion and require further technical review and prototyping before implementation._

## 1. Core Idea

To extend the Asset Organiser with a powerful **semantic search** capability. This would allow users to search their entire processed asset library using natural language queries, moving beyond simple keyword or tag-based searches.

Instead of searching for filenames like `Wood_Floor_03`, a user could search for concepts like:
- "dark weathered wooden planks"
- "clean, polished concrete floor"
- "sci-fi metal panels with glowing lights" (for 3D models)

This transforms the asset library from a static, organized collection into a dynamic, searchable knowledge base.

## 2. Proposed Architecture & Workflow

This feature would be implemented as a new, distinct service that runs after the main `Processor`.

### New Component: `Indexing Service`

- **Trigger:** The `Processor` notifies this service after successfully exporting a new batch of assets.
- **Responsibility:** To generate, store, and manage the vector embeddings for all assets.

### Workflow

1.  **Asset Ingestion:** The `Indexing Service` receives a list of newly processed assets.

2.  **Image Preparation:** For each asset, it identifies or creates a representative image:
    -   **For Texture Assets:** It uses a pre-existing, representative map (e.g., `MAP_COL` or a `PREVIEW` thumbnail).
    -   **For 3D Model Assets:** It uses a headless 3D renderer (e.g., **Blender**) to automatically generate one or more thumbnail screenshots of the model from standardized camera angles.

3.  **Vectorization:**
    -   The service uses a pre-trained **multimodal embedding model** (e.g., CLIP).
    -   This model converts each representative image into a numerical **vector**, which captures the image's semantic meaning.

4.  **Database Storage:**
    -   The generated vector, along with the **relative path to the asset's `metadata.json` file**, is stored in an **embedded vector database** (e.g., ChromaDB, FAISS). Using the metadata file as the unique identifier is robust and allows easy access to all asset information.
    -   This database is stored as a file within the main asset library directory (e.g., `../Asset_Library/.asset-library/index.db`), requiring no external setup from the user.

### The Search Process

1.  **User Query:** The user types a natural language query into a search bar in the UI.
2.  **Query Vectorization:** The backend uses the *same* embedding model to convert the user's text query into a vector.
3.  **Database Search:** The service queries the vector database to find the image vectors that are mathematically most similar to the user's query vector.
4.  **Display Results:** The database returns the paths to the matching assets, which are then fetched and displayed to the user.

## 3. Feasibility & Key Considerations

While this feature is considered highly realistic, its implementation requires careful planning.

#### Challenges
- **Application Dependencies & Size:** Bundling the embedding model, AI libraries (`torch`, `transformers`), the vector database, and a potential headless 3D renderer would significantly increase the application's distributable size.
- **Initial Indexing Performance:** The first-time indexing of a large, existing library would be a resource-intensive (CPU/GPU) and time-consuming process. This must be handled as a background task with clear user feedback.
- **Hardware Requirements:** Performance is heavily dependent on hardware. While CPU is viable, a GPU is strongly recommended for acceptable performance. The choice of model may depend on the target hardware.
- **Model Rendering Robustness:** The headless renderer for 3D models is a critical component that must be highly robust to handle a wide variety of meshes and formats without crashing.

#### Benefits
- **Transformative UX:** Moves asset management from manual browsing to intelligent discovery.
- **Future-Proofing:** Establishes a foundation for further AI-powered features, such as automatic tagging or finding duplicate/similar assets.
- **High Value:** Provides a distinct, powerful feature that sets the application apart.

## 4. User Interaction: The DCC-Native Goal

To provide a truly frictionless workflow for artists, the primary way to interact with the semantic search should be from *within* their main Digital Content Creation (DCC) software (e.g., Blender, Unreal Engine).

### API-First Design

To achieve this, the backend of the Asset Organiser must be designed as an **API-first service**. The main application itself would be a primary consumer of this API, but it would also enable the development of other clients.

### DCC Add-on

- **Concept:** A lightweight add-on or plugin would be developed for each target DCC.
- **Functionality:**
    1.  The add-on provides a native UI panel inside the DCC.
    2.  This panel communicates with the local Asset Organiser backend API to send search queries and receive results.
    3.  Upon selecting an asset from the results, the add-on uses the DCC's scripting API (e.g., Blender's `bpy`) to automatically import the asset and reconstruct its materials based on the data in its `metadata.json` file.
- **Benefit:** This approach eliminates all context-switching, allowing the artist to find and use assets from their library without ever leaving their creative environment.

Configuration: Semantic search/indexing is opt-in and controlled from the application's "Indexing" settings (see Configuration: Indexing Settings). When disabled, related UI (e.g., semantic search bar) remains hidden.


---
# Expansion - Asset Gap analysis:

>[!note]
>Keep in mind below section was written by LLM without context of full system, discrepencies may occur.

## 1. Objective

To design and develop an intelligent feature for the CG asset management engine that can dynamically analyze a user's asset library and provide actionable suggestions for missing assets.

The system must be versatile enough to cater to any CG artist (e.g., archviz, VFX, game art, concept art) without relying on static, pre-defined templates. The core technology will leverage a multimodal vector database created from asset thumbnails.

---

## 2. Core Problem Areas

We identified two distinct types of "gaps" to address:

* **Internal Gaps (Interpolation):** Finding missing concepts that lie *between* a user's existing, well-defined asset categories.
    * *Example:* A user has many `trees` and `grass` assets but lacks `bushes`.

* **External Gaps (Extrapolation):** Identifying entire categories of assets that are completely missing from a user's library but are logically relevant to their domain of work.
    * *Example:* An archviz artist has a comprehensive foliage library but no `vehicles` or `human figures`.

---

## 3. Proposed Solutions & Methodologies

### 3.1. Foundational Methods

These are the basic techniques for identifying sparse regions in the vector space:

* **Clustering Analysis:** Use algorithms like **DBSCAN** to identify points in low-density regions (noise) or **K-Means** to find large distances between cluster centroids.
* **Vector Interpolation:** To find internal gaps, calculate the midpoint vector between two related clusters (e.g., `v_midpoint = (v_trees + v_grass) / 2`). Check if this new vector lies in a sparse region. Use the multimodal model's text encoder to translate `v_midpoint` into a human-readable concept (e.g., "bush").

### 3.2. Dynamic Domain Inference (Solving for External Gaps)

To find external gaps without static templates, the system must first infer the user's domain.

* **Relational Inference Engine ("What's Next?" Model):**
    1.  **Master Knowledge Graph:** Maintain a large, pre-computed vector database of thousands of common CG text concepts.
    2.  **User Fingerprint:** Analyze the user's asset clusters to create a "fingerprint" of their primary concepts (e.g., `["sci-fi spaceship", "planet", "laser"]`).
    3.  **Suggestion via Proximity:** Query the master graph to find concepts that are semantically close to the user's fingerprint but are not present in their library (e.g., suggesting `"asteroids"` or `"space station"`).

### 3.3. Advanced Structural Analysis via Hierarchical Clustering

This approach discovers the natural, nested structure of the asset library and uses it to generate highly relevant suggestions automatically, without manual user input.

* **Core Idea:** Hierarchical clustering builds a **dendrogram** (a tree diagram) that visually represents the parent-child relationships between assets.
* **Automated Dendrogram Analysis:** The system can programmatically analyze this tree to find gaps:
    1.  **"Significant Jump" Detection:** Algorithmically find the most natural clusters by identifying the largest distances between branches in the tree. This automates the process of finding the main, distinct groups in the user's library.
    2.  **Cluster Imbalance Analysis:** Detect lopsided branches where one sub-category is highly developed and a related one is sparse (e.g., a cluster of 150 `tree` assets merging with a cluster of only 2 `fern` assets). This identifies areas for expansion.

---

## 4. Recommended Path: The "Automated Taxonomist" (Hybrid Model)

The most robust and user-friendly solution is a hybrid model that combines hierarchical analysis with the relational knowledge graph.

1.  **Auto-Discover Structure:** The system first uses **hierarchical clustering** and "significant jump" detection to automatically discover the user's main asset categories (e.g., `Foliage`, `Fantasy Weapons`) without any user input.
2.  **Identify Sub-Categories:** For each discovered parent category, it identifies the children the user possesses (e.g., within `Fantasy Weapons`, the user has `Swords` and `Axes`).
3.  **Find Missing Siblings:** It then queries the **Master Knowledge Graph** to find other common concepts belonging to that parent category (`Fantasy Weapons`) that the user is missing.
4.  **Generate Suggestion:** The system presents a clean, categorized list of suggestions to the user.

**Example User Panel Output:**
> **Collection Opportunities** 💡
>
> * In your **Fantasy Weapons** category, consider adding: `Bows`, `Magic Staffs`.
> * In your **Foliage** category, consider adding: `Bushes`, `Vines`.

This approach is fully dynamic, requires no manual configuration, and delivers highly relevant, structured suggestions by understanding the specific context of the user's collection.
