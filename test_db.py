import psycopg2

conn = psycopg2.connect(
    dbname="quick_poll_local",
    user="postgres",
    password="yowhenyow",
    host="localhost",
    port="5432"
)
print("Connection successful!")
conn.close()