# Sync safety fix and StreamHG mapping recovery

The previous version could remove StreamHG references after two file/info 404 responses and write other changes even when Abyss failed. This update blocks all mapping writes whenever any provider is unverified.

1. Temporarily disable the old CLIXARENA mapping sync workflow in GitHub Actions.
2. Copy scripts/clixarena_mapping_sync.py, scripts/clixarena_mapping_restore.py and .github/workflows/clixarena-mapping-sync.yml into the existing video-setup repo, then commit/push to the default branch. Preserve all other scripts, host-selection changes, secrets and mappings.json.
3. Open GitHub repository commit history and find the sync commit titled 'Sync confirmed deleted video host mappings' that removed the 17 references. Open it and copy its full 40-character commit SHA.
4. Enable the updated workflow. Use Run workflow, choose operation=restore_streamhg and paste that SHA into restore_sync_commit. This restores only StreamHG references removed by that commit, without replacing newer uploads, existing StreamHG IDs, other provider references or updated subtitles. It performs no uploads/deletions on video hosts. Repeated recovery is idempotent.
5. Run operation=sync only after recovery. Any incomplete provider check now leaves the entire mapping file unchanged. Safe warnings show the failing stage/status without private data. Share only those warnings if further API adaptation is needed.

New behavior:
- StreamHG requires account/info account identity, two matching file/info 404s, and matching entries in two reads of the account file/deleted list for the last 168 hours. Older missing files without deletion evidence remain mapped.
- At least five missing references representing at least 25% of any host's mapped IDs trigger a bulk-deletion guard. No writes occur.
- Any unavailable/unverified provider blocks the whole sync write; exit 1 means incomplete sync, not success.
- Abyss /v1/about validation now matches the supplied official quota sample: storageQuota, uploadQuota and maxUploadSize. Authentication uses ?key=API_KEY as explicitly documented. It does not require account id/email. GET /v1/files/:id must return the matching file ID on HTTP 200. A missing result without an explicit matching file ID is preserved rather than treated as deletion. The supplied Update info file sample describes a write endpoint; this sync never calls PUT/PATCH/DELETE or changes files at Abyss. Live GET-file/missing-file response formats remain unverified.
- GitHub file-SHA conflicts reload current mappings before a retry. Encryption/password format is unchanged.

Existing secrets: MAPPING_PASSWORD, STREAMTAPE_LOGIN, STREAMTAPE_KEY, STREAMHG_API_KEY, ABYSS_API_KEY. Built-in GitHub token has Contents write permission. No new secret is required.

17 mocked tests passed, including all-missing safety, account history cross-check, no writes on any host failure, recovery after concurrent/new uploads and repeated recovery. No live account sync, restoration or workflow run was triggered here.

Update the files in the existing video-setup repository and push. No Hugging Face or control UI changes and no new secrets are required. Keep the existing ABYSS_API_KEY. This includes the prior safety/recovery workflow. For the quota correction itself the only changed runtime file relative to the previous safety ZIP is scripts/clixarena_mapping_sync.py.
