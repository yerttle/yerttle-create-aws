import json
import boto3
import os
import logging
from datetime import datetime
from urllib.parse import unquote_plus

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
transcribe_client = boto3.client('transcribe')
s3_client = boto3.client('s3')

# Environment variables
BUCKET_NAME = os.environ.get('BUCKET_NAME', 'yerttle_tours')
LANGUAGE_CODE = os.environ.get('LANGUAGE_CODE', 'en-US')


def lambda_handler(event, context):
    """
    Lambda handler to start AWS Transcribe job when m4a file is uploaded to S3.

    Args:
        event: EventBridge event from S3 upload
        context: Lambda context object

    Returns:
        dict: Response with status code and message
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Extract S3 bucket and key from EventBridge event
        detail = event.get('detail', {})
        bucket_name = detail.get('bucket', {}).get('name', '')
        object_key = unquote_plus(detail.get('object', {}).get('key', ''))

        if not bucket_name or not object_key:
            logger.error("Missing bucket name or object key in event")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid event structure'})
            }

        logger.info(f"Processing file: s3://{bucket_name}/{object_key}")

        # Validate file extension
        if not object_key.lower().endswith('.m4a'):
            logger.warning(f"File is not .m4a format: {object_key}")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'File must be .m4a format'})
            }

        # Verify file exists in S3
        try:
            s3_client.head_object(Bucket=bucket_name, Key=object_key)
        except Exception as e:
            logger.error(f"File not found in S3: {e}")
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'File not found: {object_key}'})
            }

        # Generate unique transcription job name
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        file_name = object_key.split('/')[-1].rsplit('.', 1)[0]
        job_name = f"yerttle-{file_name}-{timestamp}"

        # Construct S3 URI for the audio file
        media_uri = f"s3://{bucket_name}/{object_key}"

        # Start transcription job
        logger.info(f"Starting transcription job: {job_name}")
        response = transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': media_uri},
            MediaFormat='m4a',
            LanguageCode=LANGUAGE_CODE,
            OutputBucketName=bucket_name,
            OutputKey=f'transcriptions/{file_name}-{timestamp}.json'
        )

        logger.info(f"Transcription job started successfully: {job_name}")
        logger.info(f"Job details: {json.dumps(response['TranscriptionJob'], default=str)}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Transcription job started successfully',
                'jobName': job_name,
                'mediaUri': media_uri,
                'outputLocation': f's3://{bucket_name}/transcriptions/{file_name}-{timestamp}.json'
            })
        }

    except transcribe_client.exceptions.BadRequestException as e:
        logger.error(f"Bad request to Transcribe: {e}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f'Bad request: {str(e)}'})
        }

    except transcribe_client.exceptions.ConflictException as e:
        logger.error(f"Transcription job already exists: {e}")
        return {
            'statusCode': 409,
            'body': json.dumps({'error': f'Job already exists: {str(e)}'})
        }

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal error: {str(e)}'})
        }
