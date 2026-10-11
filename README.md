# Retail Sales Data Platform

Portfolio project: an end-to-end retail data platform that ingests synthetic sales from CSV files, a local REST API, and operational PostgreSQL events. Python validates and loads the data into a PostgreSQL star schema; Docker runs the pipeline and Airflow schedules incremental imports. Tableau and Power BI visualize the results.

## Business question

Which products and customers drive completed sales, and how do sales change over time?

The grain of `fact_sales` is **one product line in one order**. A three-product order has three fact rows. Revenue is `quantity * unit_price` for completed lines only. Canceled orders do not contribute to revenue. Currency: ILS.

## Dashboards

The sample dashboard shows total revenue, revenue by category, monthly revenue, and revenue by product. The visuals use the synthetic warehouse data.

### Tableau

![Retail sales dashboard in Tableau](Retail%20Sales%20Overview_Tableau.png)

[Open the Tableau workbook](Retail_Sales_Overview.twb)

### Power BI

![Retail sales dashboard in Power BI](Retail%20Sales%20Overview_PowerBi.png)

[Open the Power BI report](Retail_Sales_PowerBI.pbix)

## What is implemented

1. Clean and validate historical sales CSV data, with rejected-row reports and automated tests.
2. Load validated order lines into PostgreSQL staging with Docker Compose.
3. Build a star schema with sales, customer, product, and date tables.
4. Run the historical CSV-to-warehouse pipeline with one Docker command.
5. Apply incremental CSV batches and ingest products and orders from a local REST API.
6. Schedule imports and warehouse checks with Airflow.
7. Import operational database events using a persisted watermark, query the warehouse with analytical SQL, and visualize sales in Tableau and Power BI.

## Run milestone 1

Requires Python 3.10+.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m src.clean_sales --input data/raw/sales.csv --output-dir data/output
python -m unittest discover -s tests -v
```

Outputs:

- `data/output/clean_sales.csv`: valid, normalized lines, including canceled ones.
- `data/output/fact_sales_preview.csv`: completed lines with calculated revenue.
- `data/output/rejected_sales.csv`: invalid lines with a reason for each rejection.

The sample deliberately contains a duplicate and an invalid quantity so we can see validation work. The pipeline overwrites its generated outputs each run; rerunning it does not append duplicate rows.

The automated tests use a separate fixed sample at `tests/fixtures/sales_sample.csv`. You can edit `data/raw/sales.csv` for normal runs without changing the test expectations. If you intentionally change the test sample or the business rules, update the expected results in the tests as well.

The first valid occurrence of an `(order_id, line_number)` key wins. An exact repetition is marked `duplicate order line`; a repetition with changed values is marked `conflicting duplicate order line` for investigation. This is the historical CSV policy. Updated orders in the future incremental source will have a separate upsert policy.

## Run milestone 2: PostgreSQL staging

Extract the milestone 2 ZIP to a **new folder**. Run these commands in **Windows PowerShell**, from its inner `retail-data-platform` folder (the one containing `requirements.txt` and `compose.yaml`). Keep Docker Desktop running. Python 3.10+ is required. The commands create a virtual environment inside this new project folder; no activation step is needed.

```powershell
copy .env.example .env
notepad .env
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
docker compose up -d db
docker compose ps
.\.venv\Scripts\python.exe -m src.clean_sales --input data/raw/sales_100.csv --output-dir data/output/sales_100
.\.venv\Scripts\python.exe -m src.load_sales --input data/output/sales_100/clean_sales.csv
docker compose exec db psql -U retail -d retail -c "SELECT COUNT(*) AS sales_lines FROM staging.sales_lines;"
```

In Notepad, change `POSTGRES_PASSWORD` to a password you choose and save the file. Do not commit `.env` to Git. The first Docker startup downloads the PostgreSQL image and may take a while. `docker compose ps` should show the database as healthy. The last command should return **95** rows: the sample contains 100 source rows and 5 rejected rows. Canceled but valid sales are included in staging; the later fact table will count only completed sales as revenue.

`compose.yaml` starts a local PostgreSQL 17 service. Its data lives in a named volume, so ordinary container restarts retain it. The database accepts connections only from this computer at port 5432 (or the `POSTGRES_PORT` in `.env`). If that port is already in use, edit `POSTGRES_PORT` in `.env`, then restart the service with `docker compose up -d db`.

`src/load_sales.py` reads the cleaned CSV, creates the staging table from `sql/staging.sql`, and performs a **full load**: it replaces the table's rows in one database transaction. Repeating the command gives the same row count. If the load fails, the transaction rolls back instead of leaving a half-loaded table. An empty file is rejected before replacing anything. This is a staging table, not yet the star-schema fact table.

To stop the database: `docker compose down`. This keeps the named volume and its data. `docker compose down -v` also deletes the volume and its database contents; use it only if you intentionally want to start with an empty database.

## Run milestone 3: star schema

The milestone 3 update ZIP includes `data/raw/customers.csv`, `data/raw/products.json`, `sql/warehouse.sql`, and `src/build_warehouse.py`. Extract its contents into your **existing** inner `retail-data-platform` folder, merging its `data`, `sql`, `src`, and `tests` folders. It does not include or overwrite your `.env` or `.venv`. Keep Docker Desktop running. From the same PowerShell project folder:

```powershell
docker compose ps
docker compose exec db psql -U retail -d retail -c "SELECT COUNT(*) FROM staging.sales_lines;"
.\.venv\Scripts\python.exe -m src.build_warehouse
docker compose exec db psql -U retail -d retail -c "SELECT COUNT(*) FROM dwh.fact_sales;"
Get-Content -Raw sql/analytics.sql | docker compose exec -T db psql -U retail -d retail
```

If the staging count is **95**, it is the same database from milestone 2; continue with the warehouse command. If the staging table does not exist, first run the milestone 2 clean and load commands from this folder. `src.build_warehouse` should report **20 customers, 5 products, and 90 completed sales**. Its full refresh replaces only the `dwh` tables; it does not change the 95 staging lines. It rejects missing or duplicate customer/product IDs before replacing data, and uses one transaction so errors roll back the refresh. It can be run again without duplicating sales.

### What the tables mean

| Table | One row represents | Example fields |
| --- | --- | --- |
| `staging.sales_lines` | A valid source order line, including canceled lines | `order_id`, `status`, `customer_id` |
| `dwh.dim_customer` | One customer from the CSV | Customer ID, name, city |
| `dwh.dim_product` | One product from the JSON catalog | Product ID, name, category |
| `dwh.dim_date` | One date used by completed sales | Date, year, month, day |
| `dwh.fact_sales` | One completed order line | Dimension keys, quantity, unit price, revenue |

The `customer_key` and `product_key` in the fact table refer to the dimension tables. The business IDs (`C001`, `P001`) remain in the dimensions. `date_key` is the calendar date written as an integer, such as `20260901`. Revenue is computed from the staged price and quantity, and is stored in ILS. Canceled lines remain in staging for auditing and do not appear in the fact table.

The customer names and product catalog are synthetic demonstration data. `sql/analytics.sql` uses a CTE to total revenue per product and a window function to rank products. The source CSV and JSON files can be replaced later with real sources that use the same customer and product IDs. This milestone is a full refresh; incremental updates are a later milestone.

## Run milestone 4: one-command Docker pipeline

Extract the milestone 4 update ZIP **into the existing inner project folder**. It adds `Dockerfile`, `.dockerignore`, and `src/run_pipeline.py`, and updates `compose.yaml`, `src/load_sales.py`, and `src/build_warehouse.py`. Keep your existing `.env` file. With Docker Desktop running, from that folder in PowerShell:

```powershell
docker compose run --build --rm pipeline
```

Docker builds a Python image (the first build downloads the base image and packages), waits for the PostgreSQL health check, and runs all three stages in order. The clean and rejected CSV files remain under `data/output/sales_100` on the host; PostgreSQL data remains in its Docker volume. The temporary pipeline container is removed after each run. A successful run ends with a summary of **100 source, 95 clean, 90 completed, and 5 rejected**; rerunning it refreshes the same database tables rather than duplicating rows. A failure prints a stack trace and returns a nonzero exit status.

The pipeline currently uses a full refresh and the sample input at `data/raw/sales_100.csv`. To run a different compatible CSV from the existing `data/raw` directory, override the container command, for example:

```powershell
docker compose run --build --rm pipeline python -m src.run_pipeline --input data/raw/sales.csv --output-dir data/output/sales
```

The customer CSV and product JSON must contain the IDs referenced by the chosen sales CSV. A scheduled job and incremental updates come in later milestones; this command runs the complete pipeline on demand.

## Run milestone 5a: incremental CSV batch

Extract the milestone 5a update ZIP into your **existing inner project folder**. Keep the existing `.env`, `.venv`, and PostgreSQL Docker volume. The historical pipeline must have been run at least once. With Docker Desktop running, use this command from that folder in PowerShell:

```powershell
docker compose run --build --rm pipeline python -m src.incremental_sales --input data/raw/sales_incremental.csv --output-dir data/output/incremental
```

The sample batch contains two new completed lines, a changed quantity for `2001/1`, and a cancellation for `2001/2`. It cleans the batch, updates existing lines by `(order_id, line_number)` in `staging.sales_lines`, and updates or deletes the corresponding rows in `dwh.fact_sales`. Staging, dimensions, and facts change in one database transaction. The example starting from the original 100-row file ends with **97 staging rows and 91 fact rows**; running the same batch again leaves those counts unchanged. The cleaned and rejected batch reports are under `data/output/incremental`.

For another batch, put a CSV with the same eight columns under `data/raw` and change the two paths in the command. Each batch should contain at most one valid version of a given `(order_id, line_number)`; a second conflicting version inside the *same* CSV is rejected by the cleaning rules. A later batch can update the line again. Customer and product IDs must exist in the lookup files. The full historical command in milestone 4 deliberately replaces the tables with the original historical file; run it only when you mean to rebuild that historical baseline.

This step uses an explicit CSV batch and idempotent upserts. Automatic detection of new source rows and a persisted watermark are planned for the next part of milestone 5.

## Run milestone 5b: products and orders from a REST API

Extract the milestone 5b update into the **existing inner project folder**. Keep Docker Desktop running. From that project folder in PowerShell:

```powershell
docker compose run --build --rm pipeline python -m src.import_orders_api
```

Docker Compose runs a separate `source_api` service that responds to GET `/products` and `/orders`. It serves controlled synthetic data from `data/raw` and models an external retail system. The pipeline service makes HTTP requests, parses the returned JSON into Python dictionaries, checks product IDs and sales fields, and flattens each order into sales lines. It saves the raw JSON and a flattened CSV in `data/output/api`, then uses the existing incremental loader to upsert the lines into `staging.sales_lines` and `dwh.fact_sales`. The database changes occur in one transaction. Repeating the command does not duplicate orders.

The sample has three orders and four product lines. Three lines are completed and one is canceled. Product and customer IDs match the existing lookup data; prices are in ILS. Starting from the successful 5a run (97 staging lines and 91 fact rows), this example ends with **101 staging lines and 94 fact rows**. If the sample changes, those expected counts change too.

This is a **local simulated API**, so the lesson exercises real HTTP and REST data ingestion without relying on a third-party server. It does not demonstrate third-party authentication or network reliability. The earlier public practice service returned HTTP 403 from Docker, so it is not part of this runnable milestone. A failed HTTP request or an unknown product stops the import before database changes. The HTTP response represents a source snapshot; the database load uses incremental upserts.

## Run milestone 6: Airflow scheduling

Extract this update ZIP into the **same inner `retail-data-platform` folder**. Keep your existing `.env`, `data`, and Docker database volume. From that folder in Windows PowerShell, start Docker Desktop and run:

```powershell
docker compose --profile airflow up -d --build airflow
```

This builds the Airflow image, installs the Python libraries used by the retail importer, starts PostgreSQL and the local source API if needed, and starts the Airflow scheduler and web interface. The first Airflow image download is large and can take several minutes. It **does not run the historical full refresh** and does not reset your 101 staging / 94 fact lines.

Open `http://localhost:8080` in your browser. The username is `admin`. Airflow generates a local password; after Airflow has started, get it with:

```powershell
docker compose --profile airflow exec airflow cat /opt/airflow/simple_auth_manager_passwords.json.generated
```

Find the `retail_orders_api` DAG. It has two tasks: `import_orders` requests `/products` and `/orders` from `source_api` and loads the order lines; `check_warehouse` verifies that completed staging lines and facts have matching quantities, prices and revenue. Trigger the DAG manually once in the UI and watch both tasks turn green. Because the same order keys are updated, the sample database counts should remain **101** staging lines and **94** fact lines. If a task fails, click it and open its log for the error.

Airflow writes its fetched JSON, flattened CSV, and cleaning reports under `/opt/airflow/data_output/api` in the persistent `airflow_data` Docker volume. The separate Airflow user can write there even if an earlier pipeline container created `data/output/api` on Windows with different file ownership.

The DAG is created **paused** so that you can inspect and trigger it manually first. When you are ready for automatic runs, unpause it in the UI. Its schedule is **09:00 Asia/Jerusalem every day**; `catchup=False` avoids running past days. Scheduling works only while Docker Desktop and the Airflow service are running. The API currently serves a fixed local sample, so daily runs reread the same snapshot and do not create new orders. Milestone 7 adds a source table and a persisted watermark to fetch genuinely new changes.

To stop the services, use `docker compose down` from the same project folder; it keeps the database and Airflow volumes. Avoid `docker compose down -v` unless you intend to delete the stored data. This Airflow standalone setup is for a local learning project, not a production deployment.

## Run milestone 7: an operational source in the existing database

The new source is `source.order_events` **inside the existing `retail` PostgreSQL database**. This keeps one database container and one Docker volume. The schemas have separate purposes: `source` holds incoming operational events, `staging` holds validated current order lines, `dwh` holds reporting tables, and `control` records the last event imported. In a real integration, the same importer could point its source connection at a separate operational database.

Extract this update ZIP into the **existing inner `retail-data-platform` folder**, merging `src`, `sql`, `dags`, and `tests`. Keep `.env`, `data`, and the Docker volumes. Pause `retail_orders_api` in the Airflow UI while applying the update. From the project folder in PowerShell, create the source table and four sample events:

```powershell
Get-Content -Raw sql/source_orders.sql | docker compose exec -T db psql -v ON_ERROR_STOP=1 -U retail -d retail
docker compose --profile airflow up -d --build airflow
```

The first command changes only the existing database; rerunning it does not add another copy of the sample events. The second rebuilds Airflow with the new importer and restarts it while keeping the PostgreSQL volume. Open `http://localhost:8080`, find `retail_orders_api`, and trigger it once. The DAG now runs `import_orders` (local HTTP API), `import_source_db` (new source events), then `check_warehouse`. All three tasks should turn green. Starting from **101 staging / 94 facts**, the initial four source events give **105 staging / 97 facts**: one canceled line is staged but has no fact. The `import_source_db` log reports `new_events: 4` and `last_event_id: 4`.

On the next run, the source importer reads only events with `event_id` greater than the stored watermark; with no new events it reports `new_events: 0`. A later event for an existing `(order_id, line_number)` updates or cancels that line in staging and the warehouse. The importer keeps the latest event for each line in a batch, validates the lines before loading, and commits the warehouse update and watermark together. Its JSON snapshot, flattened CSV, and cleaning reports live under `/opt/airflow/data_output/source_db` in the Airflow volume. After the manual run succeeds, unpause the DAG for the daily **09:00 Asia/Jerusalem** schedule.

Do not rerun the historical full-refresh pipeline to test this step: it replaces staging and warehouse rows with the historical CSV. Use the Airflow DAG for incremental source updates.

## Input contract

`order_id`, `line_number`, `order_date`, `customer_id`, `product_id`, `quantity`, `unit_price`, `status`.

`order_id` + `line_number` identifies a source line. Date is ISO `YYYY-MM-DD`; quantity is a positive whole number; unit price is nonnegative with at most two decimal places; status is `completed` or `canceled`. Required IDs cannot be blank.

The CSV, API, and source-table rows are demonstration data, not real customer information. The source table uses customer and product IDs from the existing lookup files.
