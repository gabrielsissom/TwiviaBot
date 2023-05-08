import sqlite3

# Open a connection to the database
conn = sqlite3.connect('channel_data.db')

# Create a cursor object
c = conn.cursor()

# Execute a SELECT statement on the channels table and print the results
c.execute('SELECT * FROM channels')
channels = c.fetchall()
print('Channels:')
for channel in channels:
    print(channel)

# Execute a SELECT statement on the users table and print the results
c.execute('SELECT * FROM users')
users = c.fetchall()
print('\nUsers:')
print("Username | Channel | Score")
for user in users:
    print(user)

# Close the cursor and the connection
c.close()
conn.close()
