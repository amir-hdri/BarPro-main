🔒 [Security Fix] Remove hardcoded default admin password and enforce secure configuration

🎯 **What:**
Fixed a security vulnerability where the `MASTER_ADMIN_PASSWORD` was hardcoded to `Amir123` in the `.env` file, and fell back to insecure defaults (`master_bar`) in the configuration files (`app/core/config.py` and `app/core/startup_validation.py`). Also removed the hardcoded default password from the frontend UI login component (`apps/web/src/app/auth/page.tsx`).

⚠️ **Risk:**
Using hardcoded and default passwords in environment variables and application code is a critical security vulnerability. If the `.env` file was exposed, or if the environment variables were not explicitly overridden in production, attackers could gain unauthorized administrative access to the entire multi-tenant system using the default master credentials (`master_bar` / `master_bar` or `admin` / `Amir123`).

🛡️ **Solution:**
1.  **Removed hardcoded password in `.env`**: Replaced `Amir123` with a securely generated random string placeholder to guide developers without leaving a guessable secret.
2.  **Enforced secure configuration in `app/core/config.py`**: Added a security validation check that raises a critical `UTCMSException` during application startup if the `MASTER_ADMIN_PASSWORD` is set to any known insecure default (`master_bar`, `admin`, `Amir123`, `password`, `123456`, `admin123`) when running in a production environment. In non-production environments, it logs a prominent warning.
3.  **Updated Startup Validation**: Enhanced `app/core/startup_validation.py` to flag insecure default passwords as a critical risk before startup.
4.  **Removed UI Default**: Cleared the default `master_bar` password state in the frontend admin login form to prevent leaking the old default password to users.
5.  **Updated Tests**: Adjusted `tests/test_master_admin.py` to mock a secure password for testing, ensuring tests pass with the new security constraints.
