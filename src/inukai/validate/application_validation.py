import os
import sys

import boto3
import click
from dotenv import load_dotenv
from loguru import logger
from types_boto3_s3.client import S3Client

from inukai.validate.application_form_validator import (
    ApplicationFormProcessor,
    read_json_from_s3,
)
from inukai.validate.bank_statement_validation import BankStatementProcessor
from inukai.validate.invoice_validation import InvoiceProcessor
from inukai.validate.validation_classes import ValidationResult

# Access the API key
load_dotenv()
GEOCODE_KEY = os.getenv("GEOCODE_KEY")

REGION = "eu-west-2"

QUERIES = {
    "What is the invoice date?": "date",
    "What is the receiver's address?": "address",
    "What is the receiver's business name?": "business_name",
    "What is the total cost?": "cost",
    "What is the good's description/name/model?": "model",
}

ERROR_MSGS = {
    "geotag_address": "The geotag information in the image does not seem to match the address on the application form.",
    "image": "The object in the image does not seem to match the object mentioned on the application form (or it is not fully captured).",
    "bank_statement": "We could not find the purchase evidence of this equipment on the bank statement.",
    "business_name": "The business name on the invoice does not seem to match the business name on the application form.",
    "address": "The address on the invoice does not seem to match the address on the application form.",
    "model": "The equipment model on the invoice does not seem to match the equipment model on the application form.",
    "date": "The date on the invoice does not seem to match the date on the application form.",
    "cost": "The cost on the invoice does not seem to match the cost on the application form.",
}


def calculate_confidence_score(
    application_form_validation_result: ValidationResult,
    bank_statement_validation_result: ValidationResult,
    invoice_validation_result: ValidationResult,
) -> float:
    sum_score = sum(
        criteria.weight * criteria.score()
        for validation_result in [
            application_form_validation_result,
            bank_statement_validation_result,
            invoice_validation_result,
        ]
        for criteria in validation_result.criteria
    )

    num_factors = sum(
        criteria.weight
        for validation_result in [
            application_form_validation_result,
            bank_statement_validation_result,
            invoice_validation_result,
        ]
        for criteria in validation_result.criteria
    )

    return sum_score / num_factors


def log_feedback(
    application_form_validation_result: ValidationResult,
    bank_statement_validation_result: ValidationResult,
    invoice_validation_result: ValidationResult,
) -> None:
    feedback_score = calculate_confidence_score(
        application_form_validation_result,
        bank_statement_validation_result,
        invoice_validation_result,
    )

    for validation_result in [
        application_form_validation_result,
        bank_statement_validation_result,
        invoice_validation_result,
    ]:
        for criteria in validation_result.criteria:
            if not criteria.score():
                logger.error(ERROR_MSGS[criteria.key])

    logger.info(f"confidence score: {feedback_score}")


class Application:
    application_form_address: dict[str, str]
    invoice_address: dict[str, str]
    bank_statement_address: dict[str, str]
    photo_address: dict[str, str | dict[str, float]]
    s3: S3Client

    def __init__(self, bucket_name: str, file_key: str) -> None:
        self.s3 = boto3.client("s3")
        application = read_json_from_s3(bucket_name, file_key, self.s3)
        self.application_form_address = application["application_form_address"]
        self.invoice_address = application["invoice_address"]
        self.bank_statement_address = application["bank_statement_address"]
        self.photo_address = application["photo_address"]

    def validate_application_form(self) -> ValidationResult:
        validator = ApplicationFormProcessor(
            application_form_address=self.application_form_address,
            photo_address=self.photo_address,
            geocode_key=GEOCODE_KEY,
        )
        return validator.validate_photo()

    def validate_bank_statement(self) -> ValidationResult:
        validator = BankStatementProcessor(
            application_form_address=self.application_form_address,
            bank_statement_address=self.bank_statement_address,
            region_name=REGION,
        )
        return validator.validate_statement()

    def validate_invoice(self) -> ValidationResult:
        invoice_processor = InvoiceProcessor(
            application_form_address=self.application_form_address,
            invoice_address=self.invoice_address,
            region_name=REGION,
            queries=QUERIES,
        )
        validation_result = invoice_processor.run_invoice_processing()
        return validation_result


@logger.catch(reraise=True)
def main(bucket_name, file_key, log_level):
    """
    Validate the application form, bank statement, and invoice using the provided BUCKET_NAME and FILE_KEY.
    """

    logger.remove()
    logger.add(sys.stderr, level=log_level.upper())

    logger.info("Starting the application validation process.")
    logger.debug(f"Received bucket_name: {bucket_name}, file_key: {file_key}")

    try:
        application = Application(bucket_name, file_key)
    except Exception as e:
        logger.error(f"Failed to initialize the application object: {e}")
        sys.exit(1)

    try:
        logger.info("Validating application form...")
        application_form_validation_result = application.validate_application_form()
        logger.success("Application form validation complete.")
    except ValueError as e:
        logger.error(f"Application form validation failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during application form validation: {e}"
        )
        sys.exit(1)

    try:
        logger.info("Validating bank statement...")
        bank_statement_validation_result = application.validate_bank_statement()
        logger.success("Bank statement validation complete.")
    except ValueError as e:
        logger.error(f"Bank statement validation failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(
            f"An unexpected error occurred during bank statement validation: {e}"
        )
        sys.exit(1)

    try:
        logger.info("Validating invoice...")
        invoice_validation_result = application.validate_invoice()
        logger.success("Invoice validation complete.")
    except ValueError as e:
        logger.error(f"Invoice validation failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred during invoice validation: {e}")
        sys.exit(1)

    try:
        logger.info("Printing feedback...")
        log_feedback(
            application_form_validation_result,
            bank_statement_validation_result,
            invoice_validation_result,
        )
        logger.success("Feedback printed successfully.")
    except ValueError as e:
        logger.error(f"Feedback logging failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"An unexpected error occurred during feedback logging: {e}")
        sys.exit(1)
