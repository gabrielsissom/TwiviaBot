import sqlite3

def print_table(table_name):
    conn = sqlite3.connect('channel_data.db')
    c = conn.cursor()
    c.execute(f'SELECT * FROM {table_name}')
    rows = c.fetchall()
    conn.close()

    print(f"\n{table_name}:")
    for row in rows:
        print(row)

def main():
    print_table("channels")
    print_table("users")
    print_table("channel_cooldowns")

if __name__ == "__main__":
    main()
