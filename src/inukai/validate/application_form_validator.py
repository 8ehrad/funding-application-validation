import io
import json
import os
import re
import sys
import tempfile
from typing import Any

import boto3
import geopy.distance
from llava.eval.run_llava import eval_model
from llava.mm_utils import get_model_name_from_path
from loguru import logger
from opencage.geocoder import OpenCageGeocode
from types_boto3_s3.client import S3Client

from inukai.validate.validation_classes import CriteriaResult, ValidationResult

MODELPATH = "liuhaotian/llava-v1.5-7b"
PROMPTTEMPLATE = (
    "There is an object in the image. Someone has claimed it is a {object}. \
                  Can you confirm the object in the image is a {object} and it is fully captured in the image? \
                  Write your response in the following format: \
                  object: True/False, fully captured: True/False"
)


def read_json_from_s3(bucket_name: str, file_key: str, s3: S3Client) -> dict[str, Any]:
    """
    Read a JSON file from S3 and returns the data.
    """
    obj = s3.get_object(Bucket=bucket_name, Key=file_key)
    data = json.loads(obj["Body"].read().decode("utf-8"))
    return data


def get_image_data(
    photo_address: dict[str, str | dict[str, float]], s3: S3Client
) -> tuple[bytes, dict[str, float]]:
    """
    Retrieve image data from S3.
    """
    bucket_name = photo_address["s3_bucket"]
    filename = photo_address["filename"]
    response = s3.get_object(Bucket=bucket_name, Key=filename)
    geotag = photo_address["geotag"]
    return response["Body"].read(), geotag


def parse_llm_response(response: str) -> tuple[bool, bool]:
    """
    Use regex to capture True/False values for 'object' and 'fully captured'
    """
    match = re.search(r"object: (\w+), fully captured: (\w+)", response)
    if match:
        object_status = match.group(1) == "True"
        fully_captured_status = match.group(2) == "True"
        return object_status, fully_captured_status
    else:
        raise ValueError("Response format is incorrect")


def capture_eval_model_output(args):
    """
    Create a string buffer to capture LLaVa's output
    """
    captured_output = io.StringIO()
    original_stdout = sys.stdout
    try:
        sys.stdout = captured_output
        eval_model(args)
        response = captured_output.getvalue().strip()
    finally:
        sys.stdout = original_stdout
    return response


class ApplicationFormProcessor:
    application_form_address: dict[str, str]
    photo_address: dict[str, str | dict[str, float]]
    application_form: dict[str, Any]
    geocode_key: str
    radius: int
    s3: S3Client

    def __init__(
        self,
        application_form_address: dict[str, str],
        photo_address: dict[str, str | dict[str, float]],
        geocode_key: str,
        radius: int = 500,
    ) -> None:
        self.s3 = boto3.client("s3")
        self.application_form_address = application_form_address
        self.photo_address = photo_address
        self.application_form = read_json_from_s3(
            application_form_address["s3_bucket"],
            application_form_address["filename"],
            self.s3,
        )
        self.geocode_key = geocode_key
        self.radius = radius

    def validate_geotag_against_address(
        self, geotag: dict[str, float], address_lat: float, address_lon: float
    ) -> tuple[bool, float]:
        """
        Validates geotag information against the address coordinates within a given radius.
        """
        geotag_coords = (geotag["latitude"], geotag["longitude"])
        address_coords = (address_lat, address_lon)
        distance = geopy.distance.geodesic(geotag_coords, address_coords).meters
        return distance <= self.radius, distance

    def get_address_coordinates(self) -> tuple[float | None, float | None]:
        """
        Use OpenCage API to get the latitude and longitude of an address.
        """
        geocoder = OpenCageGeocode(self.geocode_key)
        result = geocoder.geocode(self.application_form["address"])
        if result:
            return result[0]["geometry"]["lat"], result[0]["geometry"]["lng"]
        else:
            logger.error(f"Address not found: {self.application_form['address']}")
            return None, None

    def validate_photo(self) -> ValidationResult:
        """
        Validate the image and geotag data against the application form
        """
        validation_result = ValidationResult(component_name="ApplicationForm")
        image_data, geotag = get_image_data(self.photo_address, self.s3)
        validation_result.add_criteria(self.validate_geotag_address(geotag))
        validation_result.add_criteria(self.validate_image_contains_object(image_data))
        return validation_result

    def validate_geotag_address(self, geotag: dict[str, float]) -> CriteriaResult:
        """
        Validate geotag information captured from the photos against the
        address provided in the application forms.
        """

        address_lat, address_lon = self.get_address_coordinates()
        if address_lat is not None and address_lon is not None:
            is_within_radius, calculated_distance = (
                self.validate_geotag_against_address(geotag, address_lat, address_lon)
            )
            logger.info(
                f"Business: {self.application_form['business_name']}, Is within radius: {is_within_radius}, Distance: {calculated_distance} meters"
            )
            return CriteriaResult(key="geotag_address", value=is_within_radius)

        else:
            logger.error(
                f"Could not find coordinates for address: {self.application_form['address']}"
            )
            return CriteriaResult(key="geotag_address", value="False")

    def validate_image_contains_object(self, image_data: bytes) -> CriteriaResult:
        """
        Validate if the image associated with the application contains the specified object.
        """
        prompt = PROMPTTEMPLATE.format(object=self.application_form["item_name"])

        try:
            # Write the image data to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                tmp_file.write(image_data)
                temp_file_path = tmp_file.name
        except IOError as e:
            logger.critical(f"Failed to write image data to a temporary file: {e}")
            return CriteriaResult("image", False, weight=1)

        try:
            # Describe the image and analyze the result
            object_status, fully_captured_status = self.describe_image(
                temp_file_path, prompt
            )
        except RuntimeError as e:
            logger.error(f"Error during image description: {e}")
            object_status, fully_captured_status = False, False
        finally:
            # Ensure the temporary file is cleaned up
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except OSError as e:
                    logger.warning(
                        f"Failed to remove temporary file {temp_file_path}: {e}"
                    )

        return CriteriaResult(
            "image", object_status and fully_captured_status, weight=1
        )

    def describe_image(self, image_file_path: str, prompt: str) -> tuple[bool, bool]:
        """
        Use LLaVA to generate a description for the given image.
        """
        args = type(
            "Args",
            (),
            {
                "model_path": MODELPATH,
                "model_base": None,
                "model_name": get_model_name_from_path(MODELPATH),
                "query": prompt,
                "conv_mode": None,
                "image_file": image_file_path,
                "sep": ",",
                "temperature": 0,
                "top_p": None,
                "num_beams": 1,
                "max_new_tokens": 512,
            },
        )()
        response = capture_eval_model_output(args)
        return parse_llm_response(response)
