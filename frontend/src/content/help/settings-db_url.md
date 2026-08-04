---
id: settings.db_url
title: DB_URL
category: settings
updated_at: 2026-08-04
summary: Environment variable DB_URL. Default: mysql+pymysql://root:@localhost:3306/statejar
keywords: database db url mysql sqlite connection
---

**Environment variable:** `DB_URL`

**Default:** `mysql+pymysql://root:@localhost:3306/statejar`


The database StateJar stores state, audit rows and accounts in.

Any SQLAlchemy URL works. MySQL is the deployed default; SQLite is what the
test suite uses, and it matters more than it sounds — the default points at
MySQL, so a test run that forgets to override this pays a connection timeout
per client and takes minutes instead of seconds:

```
DB_URL="sqlite:///:memory:" python -m pytest -q
```

Changing this on a running deployment points StateJar at different data. It
does not migrate anything.
