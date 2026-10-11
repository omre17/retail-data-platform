"""Import changed orders from the local REST API and source schema."""

from datetime import timedelta

import pendulum
from airflow.sdk import DAG
from airflow.providers.standard.operators.bash import BashOperator


with DAG(
    dag_id="retail_orders_api",
    description="Import API and source table orders; check the warehouse",
    start_date=pendulum.datetime(2026, 10, 8, tz="Asia/Jerusalem"),
    schedule="0 9 * * *",
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=2)},
    tags=["retail", "rest", "incremental"],
) as dag:
    import_orders = BashOperator(
        task_id="import_orders",
        # The previous pipeline container may own /app/data/output on the host.
        # Keep Airflow's snapshots in its own writable volume instead.
        bash_command="cd /app && python -m src.import_orders_api --output-dir /opt/airflow/data_output/api",
    )

    import_source_db = BashOperator(
        task_id="import_source_db",
        bash_command="cd /app && python -m src.import_orders_db --output-dir /opt/airflow/data_output/source_db",
    )

    check_warehouse = BashOperator(
        task_id="check_warehouse",
        bash_command="cd /app && python -m src.check_warehouse",
    )

    import_orders >> import_source_db >> check_warehouse
