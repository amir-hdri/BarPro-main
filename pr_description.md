🔒 [security fix: Remove hardcoded MASTER_ADMIN_PASSWORD]

🎯 **What:**
Removed the hardcoded `MASTER_ADMIN_USERNAME` and `MASTER_ADMIN_PASSWORD` from the `.env` file.

⚠️ **Risk:**
The `.env` file contained default hardcoded credentials for the master admin (`MASTER_ADMIN_PASSWORD=Amir123`). This posed a significant security risk, as anyone with access to the source code or `.env` file could exploit these default credentials to gain full administrative access to the system, bypassing intended authentication mechanisms.

🛡️ **Solution:**
Removed the credentials completely from the root `.env` file. The application is already designed to use a secure fallback and explicitly warns administrators if default credentials are not overridden in production. By removing the hardcoded values, we ensure that proper configuration is required rather than accidentally exposing insecure defaults.
