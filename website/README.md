# Public website

Static, dependency-free website for World General Knowledge Quiz. It contains:

- `index.html` — project overview
- `privacy.html` — privacy policy
- `terms.html` — terms of service
- `assets/styles.css`, `assets/globe.svg` — local styling and artwork

There is no backend, database, analytics, cookie collection or external JavaScript. The
website is isolated from the quiz generation, TTS, rendering and publishing pipelines.

## Proposed public URLs

After GitHub Pages is configured and a deployment has succeeded, the intended URLs are:

- `https://kenethaliwanag.github.io/world-general-quiz/`
- `https://kenethaliwanag.github.io/world-general-quiz/privacy.html`
- `https://kenethaliwanag.github.io/world-general-quiz/terms.html`

These URLs are **proposed only**. They are not live and are not approved for Google OAuth
branding until Pages is enabled, deployment is verified and Google's own verification steps
are completed.

## Owner actions still required

1. **Enable Pages.** In the GitHub repository, open **Settings → Pages → Build and deployment**
   and set **Source** to **GitHub Actions**. This is required because the site lives in the
   `website/` subdirectory and is deployed by a dedicated workflow.
2. **Deploy manually.** Run the **Deploy Website to GitHub Pages** workflow from the Actions
   tab. The workflow has only a `workflow_dispatch` trigger; it will not deploy on a push,
   pull request or schedule. It uses least-privilege permissions (`contents: read`,
   `pages: write`, `id-token: write`) and uploads only `./website`.
3. **Verify the deployment.** Visit the proposed URLs and confirm all three pages and their
   links work. Only then treat them as live.
4. **Add a contact address.** No verified contact address exists in the project documentation.
   Search the website files for `CONTACT_PLACEHOLDER` and replace each placeholder block with
   a real, verified address before using the site for OAuth branding.
5. **Review the legal text.** The pages are plain-language drafts, not lawyer-reviewed legal
   advice. Review them before relying on them publicly.

## Google OAuth domain-verification limitation

GitHub Pages hosting does **not** by itself prove domain ownership for Google OAuth branding.
Google requires the owner to verify the authorized domains (for a `github.io` address, the
relevant top private domain) in Google Search Console with an account that has owner
permissions on the Cloud project. The OAuth consent screen must then use a publicly
accessible home page plus privacy policy and terms links that match the verified setup.

This repository change does not configure Google Cloud, change the OAuth client, change the
consent-screen status, or generate or replace refresh tokens. Those steps remain a manual,
owner-controlled decision after the site is hosted. See:

- https://developers.google.com/identity/verification/authentication-policy-compliance
- https://developers.google.com/identity/verification/authentication-verification

## Privacy accuracy

The privacy policy reflects the current implementation: YouTube authorization uses only the
`https://www.googleapis.com/auth/youtube.upload` scope; credentials are stored in GitHub
Actions Secrets; short-lived tokens and upload session URLs remain in memory; publication
history stores operational metadata rather than credentials; and the website itself has no
analytics or user-data collection. If the implementation changes, update `privacy.html` in the
same change.
