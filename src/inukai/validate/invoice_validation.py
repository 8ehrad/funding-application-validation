import re
from typing import Any

import boto3
import torch
import transformers
from textractor import Textractor
from textractor.data.constants import TextractFeatures
from textractor.data.text_linearization_config import TextLinearizationConfig
from types_boto3_s3.client import S3Client
from types_boto3_textract.client import TextractClient

from inukai.validate.application_form_validator import read_json_from_s3
from inukai.validate.validation_classes import CriteriaResult, ValidationResult

LLAMA_MODEL = "meta-llama/Meta-Llama-3-8B-Instruct"


class InvoiceProcessor:
    textract_client: TextractClient
    extractor: Textractor
    bucket_name: str
    document: str
    application_form: dict[str, dict[str, Any]] | dict[str, str]
    queries: dict[str, str]
    s3: S3Client

    def __init__(
        self,
        application_form_address: dict[str, str],
        invoice_address: dict[str, str],
        region_name: str,
        queries: dict[str, str],
    ) -> None:
        self.textract_client = boto3.client("textract", region_name=region_name)
        self.s3 = boto3.client("s3")
        self.extractor = Textractor(region_name=region_name)
        self.bucket_name = invoice_address["s3_bucket"]
        self.document = invoice_address["filename"]
        self.application_form = read_json_from_s3(
            application_form_address["s3_bucket"],
            application_form_address["filename"],
            self.s3,
        )
        self.queries = queries

    def analyze_document_with_queries(
        self, document_location: dict[str, dict[str, str]]
    ) -> dict[str, Any]:
        """
        Analyze the document using queries
        """
        response = self.textract_client.analyze_document(
            Document=document_location,
            FeatureTypes=["QUERIES"],
            QueriesConfig={
                "Queries": [{"Text": query} for query in self.queries.keys()]
            },
        )
        return response

    def parse_queries_response(self, response: dict[str, Any]) -> list[str]:
        """
        Parse queries response
        """
        blocks = response["Blocks"]
        output = []

        for block in blocks:
            if block["BlockType"] == "QUERY":
                query_text = block["Query"]["Text"]
                output.append({"Query": self.queries[query_text], "Answer": None})
            elif block["BlockType"] == "QUERY_RESULT":
                answer_text = block.get("Text", "")
                output[-1]["Answer"] = answer_text
        return output

    def parse_document_layout(self) -> str:
        """
        Extract layout-preserved text from a document
        """
        config = TextLinearizationConfig(
            hide_figure_layout=True, title_prefix="# ", section_header_prefix="## "
        )

        document = self.extractor.analyze_document(
            file_source=f"s3://{self.bucket_name}/{self.document}",
            features=[TextractFeatures.LAYOUT],
            save_image=True,
        )

        return document.get_text(config=config)

    def extract_validation(self, response: str) -> dict[str, str]:
        """
        Extract validation results from LLaMA response
        """
        pattern = r'"(\w+)":\s+"(MATCH|MISMATCH|NOT GIVEN)"'
        matches = re.findall(pattern, response)
        result = {key: value for key, value in matches}
        return result

    @staticmethod
    def request_to_llama(messages: list[dict[str, str]]) -> str:
        """
        Send a request to the LLaMA server containing the message parameter
        """

        pipeline = transformers.pipeline(
            "text-generation",
            model=LLAMA_MODEL,
            model_kwargs={"torch_dtype": torch.bfloat16},
            device_map="auto",
        )

        terminators = [
            pipeline.tokenizer.eos_token_id,
            pipeline.tokenizer.convert_tokens_to_ids("<|eot_id|>"),
        ]

        # Combine messages into a single string prompt
        prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])

        outputs = pipeline(
            prompt,
            max_new_tokens=256,
            eos_token_id=terminators,
            do_sample=True,
            temperature=0.6,
            top_p=0.9,
        )

        return outputs[0]["generated_text"]

    def validate_document(
        self,
        application_form: dict[str, dict[str, Any]] | dict[str, str],
        document_text: str,
    ) -> ValidationResult:
        """
        Validate the invoice against application form using LLaMA model
        """
        validation_result = ValidationResult(component_name="invoice")
        fields = (
            f"Business Name: {application_form['business_name']}\n"
            f"Model: {application_form['model']}\n"
            f"Purchase Date: {application_form['purchase_date']}\n"
            f"Cost: {application_form['cost']}\n"
            f"Address: {application_form['address']}\n\n"
        )
        json_structure = (
            "{\n"
            '  "date": "MATCH/MISMATCH",\n'
            '  "model": "MATCH/MISMATCH",\n'
            '  "cost": "MATCH/MISMATCH",\n'
            '  "address": "MATCH/MISMATCH",\n'
            '  "business_name": "MATCH/MISMATCH"\n'
            "}\n\n"
        )

        messages = [
            {
                "role": "user",
                "content": (
                    f"I have the following information from an application form:\n\n{fields}"
                    f"I want you to compare this information to the text of the following invoice "
                    f"and tell me if the information matches the above. "
                    f"Here is the invoice text:\n\n{document_text}\n\n"
                    "Use a structured format for your answer using the following template:\n\n"
                    f"{json_structure}"
                    "Please fill in the values based on the document. Your answer should be MATCH or MISMATCH."
                ),
            }
        ]

        # send a request to the llama server
        response_text = self.request_to_llama(messages)
        response_dict = self.extract_validation(response_text)

        for key, value in response_dict.items():
            validation_result.add_criteria(
                CriteriaResult(key=key, value=(value == "MATCH"))
            )

        return validation_result

    def run_invoice_processing(self) -> ValidationResult:
        """
        Extract and validate the invoice
        """
        invoice_text = self.parse_document_layout()
        return self.validate_document(self.application_form, invoice_text)
