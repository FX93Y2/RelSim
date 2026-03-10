# RelSim Walkthrough & Verification

## Installation Verified
- [x] Python dependencies installed (`python/requirements.txt`)
- [x] UI dependencies installed (`electron/package.json`)
- [x] Backend API verifies running (Port 5000)

## Consulting Firm Simulation
I have implemented a consulting firm simulation with the following components:
1.  **Database Configuration** (`python/consulting_db.yaml`): Defines `Employee` (Resource), `Company` (Client), `Project` (Entity), and supporting tables.
2.  **Simulation Configuration** (`python/consulting_sim.yaml`): Defines resource capacities and the project lifecycle flow.

### Execution
```bash
cd python
python3 main.py generate-simulate consulting_db.yaml consulting_sim.yaml -o output -n consulting
```

### Registering Project for UI
To make the manually generated simulation visible in the Electron UI, run the registration script:

```bash
python3 register_project.py
```
This script registers the project in the internal database and organizes the output files so the UI can detect them.


### Verification Results
- **Output Database**: `output/consulting.db`
- **Entities Created**: ~50 Project entities (over 100 hours simulation time).
- **Data Integrity**: Verified `Project` names and statuses are populated correctly.

### Interactive UI
The Electron application has been launched and is connected to the backend.
- **To Launch Manually**:
  1. Ensure the Python backend is running: `cd python && python3 main.py api`
  2. In a separate terminal, launch the UI: `cd electron && npm start`

### Data Export
To export all database tables to CSV format:
```bash
python3 export_to_csv.py
```
This will create a `output/csv/` directory containing CSV files for every table (e.g., `Employee.csv`, `Project.csv`).
