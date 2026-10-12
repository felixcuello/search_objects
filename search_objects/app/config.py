import os
from urllib.parse import quote_plus


def mysql_database_uri() -> str:
    """Build the SQLAlchemy URI from Compose MySQL env vars.

    The host must be the Compose service name `db`.
    """
    user = os.environ["MYSQL_USER"]
    password = quote_plus(os.environ["MYSQL_PASSWORD"])
    database = os.environ["MYSQL_DATABASE"]
    return f"mysql+pymysql://{user}:{password}@db:3306/{database}?charset=utf8mb4"


class Config:
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024
    DEFAULT_THRESHOLD = 0.3
    SQLALCHEMY_DATABASE_URI = mysql_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
