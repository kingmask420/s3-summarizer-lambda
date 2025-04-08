import os
import json
import time
import logging
import boto3
import requests

logger = logging.getLogger()
logger.setLevel(logging.INFO)

s3_client = boto3.client("s3")

MAX_POLL_ATTEMPTS = 30
POLL_SLEEP_SECONDS = 2

def lambda_handler(event, context):
    logger.info("Received event: %s", json.dumps(event))

    try:
        record = event["Records"][0]
        bucket_name = record["s3"]["bucket"]["name"]
        object_key = record["s3"]["object"]["key"]
    except (KeyError, IndexError):
        return {"statusCode": 400, "body": "Invalid event format."}

    # 1. Get text from S3
    transcription_text = get_text_from_s3(bucket_name, object_key)

    # 2. "Submit job" to Hugging Face (previously RunPod)
    #    But we'll call it 'submit_runpod_job' to keep the function name same.
    summary_result = submit_runpod_job(transcription_text)
    if not summary_result:
        logger.error("Failed to create or retrieve summarization.")
        return {"statusCode": 500, "body": "Error creating summarization via Hugging Face API."}

    # 3. Save summary to S3
    output_bucket = os.environ.get("OUTPUT_BUCKET", bucket_name)
    output_prefix = os.environ.get("OUTPUT_PREFIX", "summaries")
    output_key = f"{output_prefix}/{object_key}_summary.txt"

    put_text_to_s3(output_bucket, output_key, summary_result)

    return {
        "statusCode": 200,
        "body": f"Summary saved to s3://{output_bucket}/{output_key}"
    }


def get_text_from_s3(bucket_name, object_key):
    response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
    return response["Body"].read().decode("utf-8")


def put_text_to_s3(bucket_name, object_key, text):
    s3_client.put_object(
        Bucket=bucket_name,
        Key=object_key,
        Body=text.encode("utf-8"),
        ContentType="text/plain"
    )


# ========================= CHANGED FUNCTIONS BELOW ========================= #

def submit_runpod_job(transcription_text):
    """
    Previously: Submit job to RunPod. 
    Now: Submit transcription text to the Hugging Face Inference API 
         (mimicking an external summarization endpoint).
    We do it in one shot, returning the summary directly.
    """
    hf_api_token = os.environ.get("HF_API_TOKEN", "")
    if not hf_api_token:
        logger.error("Missing HF_API_TOKEN environment variable.")
        return None

    # We recommend a large-context model like mosaicml/mpt-30b or another model 
    # that can handle long inputs. The free tier may limit size/throughput.
    model_name = "mosaicml/mpt-30b"
    api_url = f"https://api-inference.huggingface.co/models/{model_name}"

    headers = {
        "Authorization": f"Bearer {hf_api_token}",
        "Content-Type": "application/json"
    }

    # We want ~4,000 words => ~5k tokens => set max_new_tokens = 5000
    payload = {
        "inputs": transcription_text,
        "parameters": {
            "max_new_tokens": 5000,
            "do_sample": True,
            "temperature": 0.7
        }
    }

    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=300)
        response.raise_for_status()

        # Hugging Face Inference API typically returns a list of dicts
        # like [{"generated_text": "..."}]
        data = response.json()
        summary_text = data[0].get("generated_text", "")
        logger.info("Hugging Face summarization successful.")
        return summary_text

    except requests.RequestException as e:
        logger.error(f"Error calling Hugging Face Inference API: {str(e)}")
        return None


def poll_runpod_job(job_id):
    """
    Since Hugging Face returns the summary in one synchronous call,
    we skip this function's logic. We keep it here only for reference 
    in case you truly want a /run + /status approach.

    We'll just return None to avoid logic confusion.
    """
    logger.info("poll_runpod_job called but not used in this Hugging Face version.")
    return None
