# Claude Code Instructions

## Versioning

Version strings are located in:
- Backend: `backend/src/version.py` (VERSION constant)
- App: `MorningDriveApp/src/version.ts` (APP_VERSION constant)

**Important**: Do NOT update version numbers during regular development. Version numbers should ONLY be updated when actually deploying to production (which is done by the deployment agent on the explicit request of the user).

The backend version is displayed:
- In the admin panel footer
- In the `/health` endpoint response

The app version is displayed:
- At the bottom of the Settings screen

## Deployment

- Do NOT deploy to production without asking the user first, unless they explicitly request a deployment.
- When deploying to production, increment the version numbers in the files listed above using semantic versioning (MAJOR.MINOR.PATCH).
