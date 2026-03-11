import logging
import azure.functions as func

from main import main

app = func.FunctionApp()


@app.timer_trigger(
    schedule="0 0 3 * * *",
    arg_name="mytimer",
    run_on_startup=False,
    use_monitor=True,
)
def confluence_sharepoint_sync(mytimer: func.TimerRequest) -> None:
    if mytimer.past_due:
        logging.warning("The timer trigger is past due.")

    logging.info("Azure timer triggered: confluence_sharepoint_sync")

    try:
        main()
        logging.info("Confluence -> SharePoint sync completed successfully.")
    except Exception:
        logging.exception("Confluence -> SharePoint sync failed.")
        raise