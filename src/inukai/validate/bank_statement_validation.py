from collections import defaultdict
from datetime import date
from typing import Any

import boto3
import pandas as pd
from dateutil import parser
from loguru import logger
from thefuzz import fuzz
from types_boto3_s3.client import S3Client
from types_boto3_textract.client import TextractClient

from inukai.validate.application_form_validator import read_json_from_s3
from inukai.validate.validation_classes import CriteriaResult, ValidationResult

COST_KEYWORDS = frozenset(
    [
        "out",
        "paid out",
        "money out",
        "debit",
        "payment",
        "withdrawal",
        "expense",
        "spent",
        "charge",
        "outflow",
        "amount deducted",
        "transfer out",
        "outgoing",
        "cost",
        "disbursement",
    ]
)

DATE_KEYWORDS = frozenset(["date"])

DESCRIPTION_KEYWORDS = frozenset(["description", "detail"])


class BankStatementProcessor:
    textract_client: TextractClient
    application_form: dict[str, str]
    bucket_name: str
    document: str
    s3: S3Client

    def __init__(
        self,
        application_form_address: dict[str, str],
        bank_statement_address: dict[str, str],
        region_name: str,
    ) -> None:
        self.s3 = boto3.client("s3")
        self.textract_client = boto3.client("textract", region_name=region_name)
        self.application_form = read_json_from_s3(
            application_form_address["s3_bucket"],
            application_form_address["filename"],
            self.s3,
        )
        self.bucket_name = bank_statement_address["s3_bucket"]
        self.document = bank_statement_address["filename"]

    def analyze_document_with_tables(
        self, document_location: dict[str, dict[str, str]]
    ) -> dict[str, dict[str, Any] | list[Any]]:
        """
        Analyze the bank statement with Textract and extract the table data
        """
        response = self.textract_client.analyze_document(
            Document=document_location, FeatureTypes=["TABLES"]
        )
        return response

    @staticmethod
    def parse_textract_table(
        response: dict[str, dict[str, Any] | list[Any]],
    ) -> list[list[str]]:
        """
        Parse the Textract response to extract table data
        """
        blocks = response["Blocks"]
        cells = [block for block in blocks if block["BlockType"] == "CELL"]
        items = {
            block["Id"]: block
            for block in blocks
            if block["BlockType"] in ["WORD", "LINE"]
        }

        table_data = {}
        for cell in cells:
            row = cell["RowIndex"]
            col = cell["ColumnIndex"]

            text = ""
            if "Relationships" in cell:
                for relation in cell["Relationships"]:
                    if relation["Type"] == "CHILD":
                        for child_id in relation["Ids"]:
                            if child_id in items:
                                text += items[child_id]["Text"] + " "

            text = text.strip()
            if row not in table_data:
                table_data[row] = {}
            table_data[row][col] = text

        table_rows = []
        for row in sorted(table_data.keys()):
            row_data = []
            for col in sorted(table_data[row].keys()):
                row_data.append(table_data[row][col])
            table_rows.append(row_data)

        return table_rows

    @staticmethod
    def table_to_dataframe(table_rows: list[list[str]]) -> pd.DataFrame:
        """
        Convert table rows to a DataFrame
        """
        headers = table_rows[0]
        data = table_rows[1:]
        df = pd.DataFrame(data, columns=headers)
        return df

    @staticmethod
    def map_headers(headers: list[str]) -> dict[str, str]:
        """
        Map diverse bank statement headers to standardized labels: Date, Description, Outgoing
        """

        # Initialize the mapping
        header_mapping: dict[str, str] = defaultdict(str)

        # Match headers to categories
        for header in headers:
            lower_header = header.lower()
            if any(keyword in lower_header for keyword in DATE_KEYWORDS):
                header_mapping["Date"] = header
            elif any(keyword in lower_header for keyword in DESCRIPTION_KEYWORDS):
                header_mapping["Description"] = header
            elif any(keyword in lower_header for keyword in COST_KEYWORDS):
                header_mapping["Cost"] = header

        # Check for missing mappings
        if not all(header_mapping.values()):
            raise ValueError(
                "One or more required columns (Date, Description, Cost) were not found."
            )

        return {value: key for key, value in header_mapping.items()}

    @staticmethod
    def normalize_date(date_str: str) -> date | None:
        """
        Normalize the date column format
        """
        try:
            return parser.parse(date_str).date()
        except ValueError:
            return None

    @staticmethod
    def normalize_cost(cost_str: str) -> float:
        """
        Normalize the cost column format
        """
        if cost_str == "":
            return 0.0
        cost_str = cost_str.replace("£", "")
        cost_str = cost_str.replace("$", "")
        return float(cost_str.replace(",", ""))

    def normalize_df(self, df: pd.DataFrame) -> None:
        """
        Normalize headers and converts the date and cost columns to suitable types
        """

        header_mapper = self.map_headers(df.columns)
        df.rename(columns=header_mapper, inplace=True)

        # Normalize date and cost in the DataFrame
        df["Date"] = df["Date"].apply(lambda s: self.normalize_date(s))
        df["Cost"] = df["Cost"].apply(lambda s: self.normalize_cost(s))

    @staticmethod
    def validate_business_name(description: str, business_name: str) -> int:
        """
        Validate product using fuzzy matching
        """
        return fuzz.partial_ratio(description, business_name)

    def find_matching_rows(
        self, bank_statement_df: pd.DataFrame, threshold: int = 80
    ) -> pd.DataFrame:
        """
        Find any rows on the bank statement that matches the application form
        """
        # Extract validation criteria from the application form
        target_date = self.normalize_date(self.application_form["purchase_date"])
        target_cost = self.application_form["cost"]
        target_business_name = self.application_form["business_name"]

        # Find rows with the same date and cost as claimed on the application form
        matching_rows = bank_statement_df[
            (bank_statement_df["Date"] == target_date)
            & (bank_statement_df["Cost"] == float(target_cost))
        ]

        # Validate product name similarity
        matching_rows["Business Name Match"] = matching_rows["Description"].apply(
            lambda x: self.validate_business_name(x, target_business_name)
        )

        valid_rows = matching_rows[matching_rows["Business Name Match"] >= threshold]

        return valid_rows

    def validate_statement(self) -> ValidationResult:
        """
        Main validation logic for the bank statement
        """
        validation_result = ValidationResult(component_name="BankStatement")
        document_location = {
            "S3Object": {"Bucket": self.bucket_name, "Name": self.document}
        }

        # Use Textract to extract the table and convert it into a dataframe
        response = self.analyze_document_with_tables(document_location)
        tables = self.parse_textract_table(response)
        df = self.table_to_dataframe(tables)
        self.normalize_df(df)

        # search through the bank statement for the claimed equipment
        matching_rows = self.find_matching_rows(df)

        if not matching_rows.empty:
            logger.success("Matching row found in the bank statement:")
            logger.success(matching_rows)
            validation_result.add_criteria(
                CriteriaResult(key="bank_statement", value=True, weight=3)
            )
        else:
            logger.error("No valid match found in the bank statement.")
            validation_result.add_criteria(
                CriteriaResult(key="bank_statement", value=False, weight=3)
            )

        return validation_result
