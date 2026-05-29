🔒 Fix security vulnerability: Remove hardcoded .env file

🎯 **What:** The `.env` file with hardcoded sensitive credentials (API_KEY, JWT_SECRET, DRIVER_ENCRYPTION_KEY, POSTGRES_PASSWORD, etc) was being tracked by Git.

⚠️ **Risk:** Anyone with access to the repository could read these sensitive values and compromise the application or its components. Exposing API keys and database passwords in source control is a significant security risk.

🛡️ **Solution:**
- Removed the `.env` file from Git tracking using `git rm --cached .env`.
- Added `.env` to `.gitignore` to prevent accidental commits in the future.
- Created a `.env.example` file with placeholder variables to serve as a template for developers to create their own local `.env` files without exposing real secrets.

Note: There are test failures in the test suite that are caused by a mix of dependency issues (`pydantic[email]` missing) and broken module imports (`AttributeError: module 'app.api.routes.waybill_map' has no attribute 'browser_manager'`). The test issues have been identified but kept intact since they are unrelated to this specific vulnerability fix which focuses only on the configuration files.
