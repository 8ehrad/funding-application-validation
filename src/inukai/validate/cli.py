import click
from inukai.validate.application_validation import main as main_validation

@click.command(short_help="Validate application, bank statement, and invoice.")
@click.argument(
    "bucket_name",
    type=str,
    nargs=1,
    required=True,
)
@click.argument(
    "file_key",
    type=str,
    nargs=1,
    required=True,
)
@click.option(
    "--log-level",
    "-l",
    type=click.Choice(
        ["TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"],
        case_sensitive=False,
    ),
    default="INFO",
    help="Set the logging level.",
)
def main(bucket_name, file_key, log_level):
    main_validation(bucket_name, file_key, log_level)