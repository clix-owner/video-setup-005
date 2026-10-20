# Concurrent source artifact uploads — 2026.10.20

Copy ALL .github/ and scripts/ contents into the existing repository, replacing matching files. Commit and push, including .github/actions/parallel-source-upload/dist-current and its three JavaScript bundle files plus licenses. Do not copy node_modules. No new secrets, npm install or portal redeploy required. New runs use the change when their source_commit includes this commit.

In Parallel runner mode only, the prepared source chunks upload as 1–4 concurrent GitHub artifacts, retaining existing artifact names and extraction paths. All files are checked before any transfer. All requests settle and must be confirmed before worker jobs start. Compression remains 0; retention remains 1 day. Each worker still downloads only its own source chunk. File transfers to Streamtape/StreamHG/Abyss remain sequential in the user-selected order.

The official @actions/artifact 6.3.1 SDK is pinned and bundled locally for Node 24 Actions runtime, with dependency lock and licenses. No extra install step is added to workflow runs. Includes previous download-progress and upload-wait patches. Encode settings, quality checks, success-only cleanup gates and failed-run preservation are unchanged.

Validation: 100 Python tests, 3 Node concurrency/failure tests, YAML/dependency checks; production dependency audit reports zero vulnerabilities at build time. SDK bundle loading checked locally; no authenticated artifact upload, workflow dispatch or actual host upload was performed. No measured speedup claim: shared network bandwidth, GitHub scheduling and host delays remain. Concurrent uploads can overlap transfer time; zero delay cannot be guaranteed.

Rebuild (maintainers only): run npm ci --ignore-scripts, then npm run build inside .github/actions/parallel-source-upload using the locked dependencies. Commit dist-current output and licenses.
