# test_lambda.py
import json
import pytest
from unittest.mock import patch, MagicMock
from moto import mock_s3
import boto3

import lambda_function

@mock_s3
def test_lambda_handler(monkeypatch):
    """
    1) Use monkeypatch to set environment variables 
    2) Create a new S3 client with dummy creds
    3) Monkey-patch lambda_function.s3_client
    4) Mock requests.post for Hugging Face
    5) Test
    """

    # 1) Fake AWS environment
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "FAKE_ID")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "FAKE_SECRET")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")

    # If your code references HF_API_TOKEN:
    monkeypatch.setenv("HF_API_TOKEN", "fake_hf_token")

    # 2) Create our own S3 client with fake creds
    test_s3 = boto3.client(
        "s3", 
        region_name="us-east-1",
        aws_access_key_id="FAKE_ID",
        aws_secret_access_key="FAKE_SECRET"
    )

    # 3) Monkey-patch the global s3_client in lambda_function
    monkeypatch.setattr(lambda_function, "s3_client", test_s3)

    # Now create bucket, etc. with that S3 client
    bucket_name = "test-bucket"
    test_s3.create_bucket(Bucket=bucket_name)
    file_key = "example.txt"
    file_content = "Large transcription text"
    test_s3.put_object(Bucket=bucket_name, Key=file_key, Body=file_content)

    # 4) Mock the Hugging Face request
    with patch("lambda_function.requests.post") as mock_post:
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [
            {"generated_text": "This is the mocked summary"}
        ]
        mock_post.return_value = mock_response

        # 5) Build a fake S3 event
        fake_event = {
            "Records": [
                {
                    "s3": {
                        "bucket": {"name": bucket_name},
                        "object": {"key": file_key},
                    }
                }
            ]
        }

        response = lambda_function.lambda_handler(fake_event, None)
        print("Lambda response:", response)

        assert response["statusCode"] == 200
        assert "Summary saved to s3://" in response["body"]
        mock_post.assert_called_once()

        # Check the summary was written
        out_key = f"summaries/{file_key}_summary.txt"
        obj = test_s3.get_object(Bucket=bucket_name, Key=out_key)
        summary_text = obj["Body"].read().decode("utf-8")

        # Make sure the summary is the one we mocked
        assert summary_text == "This is the mocked summary"
