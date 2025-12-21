import src.rts_world.db.db as db


def main():
    conn = db.get_connection()

    with conn.cursor() as cur:
        cur.execute("SELECT * FROM characters;")
        
        result = cur.fetchall()

        print(result)


main()