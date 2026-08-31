# cPanel/shared hosting has no libmysqlclient, so MySQL runs through the pure
# Python PyMySQL driver. Harmless when PyMySQL is absent (Postgres/SQLite).
try:
    import pymysql
except ImportError:  # pragma: no cover - driver optional per environment
    pass
else:
    pymysql.install_as_MySQLdb()
