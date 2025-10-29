import json
import boto3
import os
import logging
from datetime import datetime
from urllib.parse import urlparse
import gzip

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
comprehend_client = boto3.client('comprehend')

# Environment variables
BUCKET_NAME = os.environ.get('BUCKET_NAME', 'yerttle-tours')
SENTIMENT_PREFIX = os.environ.get('SENTIMENT_PREFIX', 'sentiment/')


def lambda_handler(event, context):
    """
    Lambda handler to process completed async Comprehend jobs.
    Aggregates results from sentiment, entities, and key phrases detection.

    Args:
        event: EventBridge event from Comprehend job completion
        context: Lambda context object

    Returns:
        dict: Response with status code and message
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Extract job details from EventBridge event
        detail = event.get('detail', {})
        job_id = detail.get('JobId', '')
        job_status = detail.get('JobStatus', '')
        event_type = event.get('detail-type', '')

        if not job_id:
            logger.error("Missing JobId in event")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid event structure'})
            }

        logger.info(f"Processing job: {job_id}, Status: {job_status}, Type: {event_type}")

        # Only process completed jobs
        if job_status != 'COMPLETED':
            logger.warning(f"Job {job_id} status is {job_status}, skipping processing")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'Job status is {job_status}, no action taken',
                    'jobId': job_id
                })
            }

        # Determine job type and process accordingly
        if 'Sentiment' in event_type:
            result = process_sentiment_job(job_id)
        elif 'Entities' in event_type:
            result = process_entities_job(job_id)
        elif 'Key Phrases' in event_type:
            result = process_key_phrases_job(job_id)
        else:
            logger.error(f"Unknown job type: {event_type}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': f'Unknown job type: {event_type}'})
            }

        # After processing individual job, check if all jobs are complete
        # and aggregate results if they are
        try:
            aggregate_results_if_complete(result.get('analysisId'))
        except Exception as e:
            logger.warning(f"Failed to aggregate results: {e}")

        return {
            'statusCode': 200,
            'body': json.dumps(result)
        }

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal error: {str(e)}'})
        }


def process_sentiment_job(job_id):
    """
    Process completed sentiment detection job.

    Args:
        job_id: Comprehend job ID

    Returns:
        dict: Job results
    """
    try:
        logger.info(f"Processing sentiment job: {job_id}")

        # Get job details
        response = comprehend_client.describe_sentiment_detection_job(JobId=job_id)
        job = response.get('SentimentDetectionJobProperties', {})

        output_location = job.get('OutputDataConfig', {}).get('S3Uri', '')
        job_name = job.get('JobName', '')

        logger.info(f"Job name: {job_name}, Output: {output_location}")

        # Read and parse output file
        results = read_comprehend_output(output_location)

        # Extract analysis ID from job name (format: sentiment-{analysis_id})
        analysis_id = job_name.replace('sentiment-', '')

        # Save individual results
        output_key = f"{SENTIMENT_PREFIX}{analysis_id}-sentiment-result.json"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=output_key,
            Body=json.dumps(results, indent=2, default=str),
            ContentType='application/json'
        )

        logger.info(f"Sentiment results saved to: s3://{BUCKET_NAME}/{output_key}")

        return {
            'message': 'Sentiment job processed successfully',
            'jobId': job_id,
            'jobName': job_name,
            'analysisId': analysis_id,
            'outputLocation': f's3://{BUCKET_NAME}/{output_key}'
        }

    except Exception as e:
        logger.error(f"Failed to process sentiment job: {e}", exc_info=True)
        raise


def process_entities_job(job_id):
    """
    Process completed entities detection job.

    Args:
        job_id: Comprehend job ID

    Returns:
        dict: Job results
    """
    try:
        logger.info(f"Processing entities job: {job_id}")

        # Get job details
        response = comprehend_client.describe_entities_detection_job(JobId=job_id)
        job = response.get('EntitiesDetectionJobProperties', {})

        output_location = job.get('OutputDataConfig', {}).get('S3Uri', '')
        job_name = job.get('JobName', '')

        logger.info(f"Job name: {job_name}, Output: {output_location}")

        # Read and parse output file
        results = read_comprehend_output(output_location)

        # Extract analysis ID from job name
        analysis_id = job_name.replace('entities-', '')

        # Save individual results
        output_key = f"{SENTIMENT_PREFIX}{analysis_id}-entities-result.json"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=output_key,
            Body=json.dumps(results, indent=2, default=str),
            ContentType='application/json'
        )

        logger.info(f"Entities results saved to: s3://{BUCKET_NAME}/{output_key}")

        return {
            'message': 'Entities job processed successfully',
            'jobId': job_id,
            'jobName': job_name,
            'analysisId': analysis_id,
            'outputLocation': f's3://{BUCKET_NAME}/{output_key}'
        }

    except Exception as e:
        logger.error(f"Failed to process entities job: {e}", exc_info=True)
        raise


def process_key_phrases_job(job_id):
    """
    Process completed key phrases detection job.

    Args:
        job_id: Comprehend job ID

    Returns:
        dict: Job results
    """
    try:
        logger.info(f"Processing key phrases job: {job_id}")

        # Get job details
        response = comprehend_client.describe_key_phrases_detection_job(JobId=job_id)
        job = response.get('KeyPhrasesDetectionJobProperties', {})

        output_location = job.get('OutputDataConfig', {}).get('S3Uri', '')
        job_name = job.get('JobName', '')

        logger.info(f"Job name: {job_name}, Output: {output_location}")

        # Read and parse output file
        results = read_comprehend_output(output_location)

        # Extract analysis ID from job name
        analysis_id = job_name.replace('key-phrases-', '')

        # Save individual results
        output_key = f"{SENTIMENT_PREFIX}{analysis_id}-keyphrases-result.json"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=output_key,
            Body=json.dumps(results, indent=2, default=str),
            ContentType='application/json'
        )

        logger.info(f"Key phrases results saved to: s3://{BUCKET_NAME}/{output_key}")

        return {
            'message': 'Key phrases job processed successfully',
            'jobId': job_id,
            'jobName': job_name,
            'analysisId': analysis_id,
            'outputLocation': f's3://{BUCKET_NAME}/{output_key}'
        }

    except Exception as e:
        logger.error(f"Failed to process key phrases job: {e}", exc_info=True)
        raise


def read_comprehend_output(s3_uri):
    """
    Read and parse Comprehend output file from S3.
    Output files are typically gzipped JSON.

    Args:
        s3_uri: S3 URI to the output file

    Returns:
        dict: Parsed output data
    """
    try:
        # Parse S3 URI
        parsed = urlparse(s3_uri)
        bucket = parsed.netloc
        prefix = parsed.path.lstrip('/')

        logger.info(f"Looking for output files in: s3://{bucket}/{prefix}")

        # List files in output location (Comprehend creates files with random names)
        response = s3_client.list_objects_v2(
            Bucket=bucket,
            Prefix=prefix
        )

        # Find the output.tar.gz or .out files
        output_files = [
            obj['Key'] for obj in response.get('Contents', [])
            if obj['Key'].endswith('.out') or obj['Key'].endswith('.gz')
        ]

        if not output_files:
            logger.error(f"No output files found in {s3_uri}")
            return {}

        # Read the first output file
        output_key = output_files[0]
        logger.info(f"Reading output file: s3://{bucket}/{output_key}")

        obj = s3_client.get_object(Bucket=bucket, Key=output_key)
        content = obj['Body'].read()

        # Try to decompress if gzipped
        try:
            content = gzip.decompress(content)
        except:
            pass  # Not gzipped

        # Parse JSON (output is typically one JSON object per line)
        lines = content.decode('utf-8').strip().split('\n')
        results = []
        for line in lines:
            if line.strip():
                results.append(json.loads(line))

        logger.info(f"Parsed {len(results)} result records")

        return results[0] if len(results) == 1 else results

    except Exception as e:
        logger.error(f"Failed to read Comprehend output: {e}", exc_info=True)
        return {}


def aggregate_results_if_complete(analysis_id):
    """
    Check if all three jobs are complete and aggregate results.

    Args:
        analysis_id: Unique identifier for the analysis

    Returns:
        bool: True if all results aggregated, False otherwise
    """
    try:
        if not analysis_id:
            return False

        logger.info(f"Checking if all jobs complete for analysis: {analysis_id}")

        # Check for all three result files
        sentiment_key = f"{SENTIMENT_PREFIX}{analysis_id}-sentiment-result.json"
        entities_key = f"{SENTIMENT_PREFIX}{analysis_id}-entities-result.json"
        keyphrases_key = f"{SENTIMENT_PREFIX}{analysis_id}-keyphrases-result.json"

        sentiment_exists = object_exists(BUCKET_NAME, sentiment_key)
        entities_exists = object_exists(BUCKET_NAME, entities_key)
        keyphrases_exists = object_exists(BUCKET_NAME, keyphrases_key)

        logger.info(f"Results status - Sentiment: {sentiment_exists}, "
                   f"Entities: {entities_exists}, KeyPhrases: {keyphrases_exists}")

        if not (sentiment_exists and entities_exists and keyphrases_exists):
            logger.info("Not all jobs complete yet, skipping aggregation")
            return False

        logger.info("All jobs complete, aggregating results...")

        # Read all results
        sentiment_data = read_json_from_s3(BUCKET_NAME, sentiment_key)
        entities_data = read_json_from_s3(BUCKET_NAME, entities_key)
        keyphrases_data = read_json_from_s3(BUCKET_NAME, keyphrases_key)

        # Read metadata if exists
        metadata_key = f"{SENTIMENT_PREFIX}{analysis_id}-metadata.json"
        metadata = {}
        if object_exists(BUCKET_NAME, metadata_key):
            metadata = read_json_from_s3(BUCKET_NAME, metadata_key)

        # Aggregate results
        aggregated_results = {
            'analysisId': analysis_id,
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'analysisType': 'asynchronous',
            'transcriptionFile': metadata.get('transcriptionFile', ''),
            'textLength': metadata.get('textLength', 0),
            'textBytes': metadata.get('textBytes', 0),
            'sentiment': sentiment_data,
            'entities': entities_data,
            'keyPhrases': keyphrases_data,
            'metadata': metadata
        }

        # Save aggregated results
        output_key = f"{SENTIMENT_PREFIX}{analysis_id}-analysis.json"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=output_key,
            Body=json.dumps(aggregated_results, indent=2, default=str),
            ContentType='application/json',
            Metadata={
                'analysis-id': analysis_id,
                'analysis-type': 'asynchronous',
                'status': 'COMPLETED'
            }
        )

        logger.info(f"Aggregated results saved to: s3://{BUCKET_NAME}/{output_key}")

        return True

    except Exception as e:
        logger.error(f"Failed to aggregate results: {e}", exc_info=True)
        return False


def object_exists(bucket, key):
    """
    Check if an S3 object exists.

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        bool: True if object exists, False otherwise
    """
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except:
        return False


def read_json_from_s3(bucket, key):
    """
    Read and parse JSON file from S3.

    Args:
        bucket: S3 bucket name
        key: S3 object key

    Returns:
        dict: Parsed JSON data
    """
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        return json.loads(response['Body'].read().decode('utf-8'))
    except Exception as e:
        logger.error(f"Failed to read JSON from s3://{bucket}/{key}: {e}")
        return {}
