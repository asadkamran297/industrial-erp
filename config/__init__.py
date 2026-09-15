try:
    import pymysql
except ImportError:  # pragma: no cover - driver optional per environment
    pass
else:
    pymysql.install_as_MySQLdb()
