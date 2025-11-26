import psycopg
import os
import dotenv

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

host = os.getenv("DB_HOST")


def get_connection():
    return psycopg.connect(
        host = DB_HOST,
        port = DB_PORT,
        dbname = DB_NAME,
        user = DB_USER,
        password = DB_PASSWORD
    )

