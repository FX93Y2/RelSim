
import sqlite3
import uuid
import datetime
import os
import shutil

DB_PATH = 'python/config_storage/configs.db'
OUTPUT_BASE = 'output'
CONSULTING_DB = 'output/consulting.db'

# Generate IDs
project_id = str(uuid.uuid4())
db_config_id = str(uuid.uuid4())
sim_config_id = str(uuid.uuid4())
now = datetime.datetime.now().isoformat()

# Content
with open('python/consulting_db.yaml', 'r') as f:
    db_yaml = f.read()
with open('python/consulting_sim.yaml', 'r') as f:
    sim_yaml = f.read()

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

# Insert Project
print(f"Creating project with ID: {project_id}")
c.execute("INSERT INTO projects (id, name, description, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
          (project_id, 'Consulting Firm', 'Simulation of a consulting firm', now, now))

# Insert Configs
c.execute("INSERT INTO configs (id, name, type, content, description, project_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
          (db_config_id, 'Consulting DB', 'database', db_yaml, 'Database configuration', project_id, now, now))

c.execute("INSERT INTO configs (id, name, type, content, description, project_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
          (sim_config_id, 'Consulting Sim', 'simulation', sim_yaml, 'Simulation configuration', project_id, now, now))

conn.commit()
conn.close()

# Setup Output Directory
project_out_dir = os.path.join(OUTPUT_BASE, project_id)
os.makedirs(project_out_dir, exist_ok=True)

# Copy DB
shutil.copy(CONSULTING_DB, os.path.join(project_out_dir, 'consulting.db'))
# Also copy as database.db as a fallback if the UI expects a standard name, 
# though based on the code it might scan for extensions
shutil.copy(CONSULTING_DB, os.path.join(project_out_dir, 'database.db'))

print(f"Project output setup at: {project_out_dir}")
