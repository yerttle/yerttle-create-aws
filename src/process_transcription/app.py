import json
import boto3
import os
import logging
from urllib.parse import urlparse
import urllib.request

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
transcribe_client = boto3.client('transcribe')
s3_client = boto3.client('s3')

# Environment variables
BUCKET_NAME = os.environ.get('BUCKET_NAME', 'yerttle-tours')


def lambda_handler(event, context):
    """
    Lambda handler to process completed AWS Transcribe job.
    Logs completion and can be extended for notifications or additional processing.

    Args:
        event: EventBridge event from Transcribe job completion
        context: Lambda context object

    Returns:
        dict: Response with status code and message
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Extract transcription job details from EventBridge event
        detail = event.get('detail', {})
        job_name = detail.get('TranscriptionJobName', '')
        job_status = detail.get('TranscriptionJobStatus', '')

        if not job_name:
            logger.error("Missing TranscriptionJobName in event")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid event structure'})
            }

        logger.info(f"Processing transcription job: {job_name}, Status: {job_status}")

        # Only process completed jobs
        if job_status != 'COMPLETED':
            logger.warning(f"Job {job_name} status is {job_status}, skipping processing")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': f'Job status is {job_status}, no action taken',
                    'jobName': job_name
                })
            }

        # Get detailed job information
        response = transcribe_client.get_transcription_job(
            TranscriptionJobName=job_name
        )

        job_details = response.get('TranscriptionJob', {})
        transcript_file_uri = job_details.get('Transcript', {}).get('TranscriptFileUri', '')
        media_file_uri = job_details.get('Media', {}).get('MediaFileUri', '')

        if not transcript_file_uri:
            logger.error(f"No transcript file URI found for job {job_name}")
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Transcript file URI not found'})
            }

        logger.info(f"Transcript URI: {transcript_file_uri}")

        # Fetch transcript content from Transcribe's managed storage
        # The URI is a pre-signed URL that we can fetch via HTTPS
        try:
            with urllib.request.urlopen(transcript_file_uri) as response:
                transcript_content = json.loads(response.read().decode('utf-8'))
                file_size = len(json.dumps(transcript_content))
                logger.info(f"Transcript file size: {file_size} bytes")

            # Extract transcript text for logging
            transcript_text = transcript_content.get('results', {}).get('transcripts', [{}])[0].get('transcript', '')
            word_count = len(transcript_text.split()) if transcript_text else 0

            logger.info(f"Transcription completed successfully:")
            logger.info(f"  - Job Name: {job_name}")
            logger.info(f"  - Source Audio: {media_file_uri}")
            logger.info(f"  - Transcript URI: {transcript_file_uri}")
            logger.info(f"  - Word Count: {word_count}")
            logger.info(f"  - Transcript Preview: {transcript_text[:200]}...")

            # Copy transcription to our bucket to trigger sentiment analysis
            destination_key = f"transcriptions/{job_name}.json"
            try:
                s3_client.put_object(
                    Bucket=BUCKET_NAME,
                    Key=destination_key,
                    Body=json.dumps(transcript_content),
                    ContentType='application/json'
                )
                logger.info(f"Copied transcription to s3://{BUCKET_NAME}/{destination_key}")
            except Exception as copy_error:
                logger.error(f"Failed to copy transcription to our bucket: {copy_error}")
                # Continue processing even if copy fails

            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Transcription processed successfully',
                    'jobName': job_name,
                    'transcriptUri': transcript_file_uri,
                    'copiedTo': f's3://{BUCKET_NAME}/{destination_key}',
                    'mediaUri': media_file_uri,
                    'wordCount': word_count,
                    'fileSize': file_size
                })
            }

        except Exception as e:
            logger.error(f"Failed to read transcript content: {e}")
            return {
                'statusCode': 500,
                'body': json.dumps({
                    'message': 'Failed to fetch or process transcript',
                    'jobName': job_name,
                    'transcriptUri': transcript_file_uri,
                    'error': str(e)
                })
            }

    except transcribe_client.exceptions.BadRequestException as e:
        logger.error(f"Bad request to Transcribe: {e}")
        return {
            'statusCode': 400,
            'body': json.dumps({'error': f'Bad request: {str(e)}'})
        }

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal error: {str(e)}'})
        }
