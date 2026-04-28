import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import pandas as pd
import time
import mysql.connector

# ─────────────────────────────────────────
# 1. Spotify Credentials
# ─────────────────────────────────────────
CLIENT_ID     = 'your client id'
CLIENT_SECRET = 'your client secret'

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET
    ),
    requests_timeout=10
)

# ─────────────────────────────────────────
# 2. MySQL Connection
# ─────────────────────────────────────────
connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="yourpassword",
    database="spotify_db"
)
cursor = connection.cursor()

# ─────────────────────────────────────────
# 3. Create Table
# ─────────────────────────────────────────
def create_table():
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spotify_tracks (
            spotify_id      VARCHAR(50)  PRIMARY KEY,
            track_name      VARCHAR(255),
            artist          VARCHAR(255),
            album           VARCHAR(255),
            release_date    VARCHAR(20),
            duration_min    FLOAT,
            source_playlist VARCHAR(100)
        )
    """)
    connection.commit()

    try:
        cursor.execute("ALTER TABLE spotify_tracks ADD COLUMN source_playlist VARCHAR(100)")
        connection.commit()
    except Exception:
        pass

    try:
        cursor.execute("ALTER TABLE spotify_tracks DROP COLUMN popularity")
        connection.commit()
    except Exception:
        pass

    print("Table ready.\n")


# ─────────────────────────────────────────
# 4. India-Only Search Queries
#    Covers all major Indian music markets:
#    Bollywood, Tamil, Telugu, Malayalam,
#    Kannada, Punjabi, Bengali, Bhojpuri
# ─────────────────────────────────────────
SEARCH_QUERIES = [
    # Bollywood / Hindi
    '2024 bollywood hits',
    '2024 hindi songs',
    'new hindi songs 2024',
    'bollywood 2024',

    # South Indian
    '2024 tamil songs',
    '2024 tamil hits',
    'new tamil songs 2024',
    '2024 telugu hits',
    'new telugu songs 2024',
    '2024 malayalam hits',
    '2024 kannada hits',

    # Punjabi
    '2024 punjabi songs',
    'new punjabi songs 2024',
    '2024 punjabi hits',

    # Regional
    '2024 bengali songs',
    '2024 bhojpuri hits',
    '2024 marathi songs',

    # Top Indian Artists (ensures their 2024 releases are captured)
    'arijit singh 2024',
    'shreya ghoshal 2024',
    'vishal mishra 2024',
    'anirudh ravichander 2024',
    'sachin jigar 2024',
    'karan aujla 2024',
    'diljit dosanjh 2024',
    'ap dhillon 2024',
    'badshah 2024',
    'yo yo honey singh 2024',
]

# ─────────────────────────────────────────
# 5. Fetch Tracks
# ─────────────────────────────────────────
def fetch_by_search(target_year, total_to_collect=300):
    all_tracks = []
    seen_ids   = set()
    limit      = 5

    print(f"Searching for Indian {target_year} tracks...\n")

    for query in SEARCH_QUERIES:
        if len(all_tracks) >= total_to_collect:
            break

        for offset in range(0, 50, limit):
            if len(all_tracks) >= total_to_collect:
                break

            try:
                results = sp.search(
                    q=query,
                    type='track',
                    limit=limit,
                    offset=offset
                )

                items = results['tracks']['items']
                if not items:
                    break

                for track in items:
                    sid = track['id']
                    if sid in seen_ids:
                        continue
                    seen_ids.add(sid)

                    release = track['album']['release_date']
                    if not release.startswith(str(target_year)):
                        continue

                    all_tracks.append({
                        'spotify_id':      sid,
                        'track_name':      track['name'],
                        'artist':          track['artists'][0]['name'],
                        'album':           track['album']['name'],
                        'release_date':    release,
                        'duration_min':    round(track['duration_ms'] / 60000, 2),
                        'source_playlist': f'Search: {query}',
                    })

                time.sleep(0.5)

            except Exception as e:
                print(f"  Error (query='{query}', offset={offset}): {e}")
                time.sleep(2)
                break

        print(f"  '{query}' done | total: {len(all_tracks)}")
        time.sleep(1)

    print(f"\nDone. Total unique Indian {target_year} tracks: {len(all_tracks)}")
    return pd.DataFrame(all_tracks)


# ─────────────────────────────────────────
# 6. Insert into MySQL
# ─────────────────────────────────────────
def insert_into_mysql(df):
    if df.empty:
        print("Nothing to insert.")
        return

    insert_query = """
        INSERT INTO spotify_tracks
            (spotify_id, track_name, artist, album,
             release_date, duration_min, source_playlist)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            track_name      = VALUES(track_name),
            album           = VALUES(album),
            duration_min    = VALUES(duration_min),
            source_playlist = VALUES(source_playlist)
    """

    count = 0
    for _, row in df.iterrows():
        cursor.execute(insert_query, (
            row['spotify_id'],
            row['track_name'],
            row['artist'],
            row['album'],
            row['release_date'],
            row['duration_min'],
            row['source_playlist'],
        ))
        count += 1

    connection.commit()
    print(f"{count} records inserted / updated in MySQL.")


# ─────────────────────────────────────────
# 7. Run
# ─────────────────────────────────────────
if __name__ == "__main__":
    target_year = 2024

    create_table()

    df_final = fetch_by_search(target_year, total_to_collect=300)

    if not df_final.empty:
        print("\nBreakdown by search query:")
        for src, cnt in df_final['source_playlist'].value_counts().items():
            print(f"  {src}: {cnt} tracks")

        csv_path = f'spotify_india_{target_year}.csv'
        df_final.to_csv(csv_path, index=False)
        print(f"\nCSV saved → {csv_path}")

        insert_into_mysql(df_final)
        print("SUCCESS: All Indian data inserted into MySQL.")
    else:
        print("\nNo data collected.")
        print("Check: 1) credentials  2) internet connection  3) Spotify app is active")

    cursor.close()
    connection.close()
