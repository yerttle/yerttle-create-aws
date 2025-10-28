import json
import boto3
import os
import logging
from datetime import datetime
from urllib.parse import unquote_plus, urlparse
import uuid

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
comprehend_client = boto3.client('comprehend')

# Environment variables
BUCKET_NAME = os.environ.get('BUCKET_NAME', 'yerttle_tours')
LANGUAGE_CODE = os.environ.get('LANGUAGE_CODE', 'en-US')
SENTIMENT_PREFIX = os.environ.get('SENTIMENT_PREFIX', 'sentiment/')
COMPREHEND_ROLE_ARN = os.environ.get('COMPREHEND_ROLE_ARN')

# Comprehend synchronous API limit
SYNC_API_LIMIT_BYTES = 5000


def lambda_handler(event, context):
    """
    Lambda handler to analyze transcription using AWS Comprehend.
    Performs sentiment analysis, entity detection, and key phrase extraction.

    Args:
        event: EventBridge event from S3 transcription JSON creation
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

        logger.info(f"Processing transcription: s3://{bucket_name}/{object_key}")

        # Read transcription JSON from S3
        try:
            response = s3_client.get_object(Bucket=bucket_name, Key=object_key)
            transcription_data = json.loads(response['Body'].read().decode('utf-8'))
        except Exception as e:
            logger.error(f"Failed to read transcription file: {e}")
            return {
                'statusCode': 404,
                'body': json.dumps({'error': f'Failed to read transcription: {str(e)}'})
            }

        # Extract transcript text
        transcript_text = transcription_data.get('results', {}).get('transcripts', [{}])[0].get('transcript', '')

        if not transcript_text:
            logger.warning("No transcript text found in JSON")
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'No transcript text found'})
            }

        # Check text size
        text_bytes = len(transcript_text.encode('utf-8'))
        logger.info(f"Transcript size: {text_bytes} bytes ({len(transcript_text)} characters)")

        # Generate unique identifier for this analysis
        timestamp = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
        file_name = object_key.split('/')[-1].rsplit('.', 1)[0]
        analysis_id = f"{file_name}-{timestamp}"

        if text_bytes <= SYNC_API_LIMIT_BYTES:
            # Use synchronous APIs for small texts
            logger.info("Using synchronous Comprehend APIs")
            result = process_synchronous_analysis(
                transcript_text,
                analysis_id,
                object_key,
                bucket_name
            )
        else:
            # Use asynchronous APIs for large texts
            logger.info("Using asynchronous Comprehend APIs")
            result = process_asynchronous_analysis(
                transcript_text,
                analysis_id,
                object_key,
                bucket_name
            )

        return result

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal error: {str(e)}'})
        }


def process_synchronous_analysis(text, analysis_id, transcription_key, bucket_name):
    """
    Process text using synchronous Comprehend APIs.

    Args:
        text: The transcript text to analyze
        analysis_id: Unique identifier for this analysis
        transcription_key: S3 key of the transcription file
        bucket_name: S3 bucket name

    Returns:
        dict: Response with status code and message
    """
    try:
        logger.info("Starting synchronous Comprehend analysis...")

        # Detect sentiment
        logger.info("Detecting sentiment...")
        sentiment_response = comprehend_client.detect_sentiment(
            Text=text,
            LanguageCode=LANGUAGE_CODE
        )

        # Detect entities
        logger.info("Detecting entities...")
        entities_response = comprehend_client.detect_entities(
            Text=text,
            LanguageCode=LANGUAGE_CODE
        )

        # Detect key phrases
        logger.info("Detecting key phrases...")
        key_phrases_response = comprehend_client.detect_key_phrases(
            Text=text,
            LanguageCode=LANGUAGE_CODE
        )

        # Compile results
        analysis_results = {
            'analysisId': analysis_id,
            'transcriptionFile': f's3://{bucket_name}/{transcription_key}',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'textLength': len(text),
            'textBytes': len(text.encode('utf-8')),
            'analysisType': 'synchronous',
            'sentiment': {
                'Sentiment': sentiment_response.get('Sentiment'),
                'SentimentScore': sentiment_response.get('SentimentScore', {})
            },
            'entities': {
                'Entities': entities_response.get('Entities', []),
                'Count': len(entities_response.get('Entities', []))
            },
            'keyPhrases': {
                'KeyPhrases': key_phrases_response.get('KeyPhrases', []),
                'Count': len(key_phrases_response.get('KeyPhrases', []))
            },
            'metadata': {
                'languageCode': LANGUAGE_CODE,
                'processingTimestamp': datetime.utcnow().isoformat() + 'Z'
            }
        }

        # Save results to S3
        output_key = f"{SENTIMENT_PREFIX}{analysis_id}-analysis.json"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=output_key,
            Body=json.dumps(analysis_results, indent=2, default=str),
            ContentType='application/json',
            Metadata={
                'analysis-id': analysis_id,
                'sentiment': sentiment_response.get('Sentiment', ''),
                'entity-count': str(len(entities_response.get('Entities', []))),
                'key-phrase-count': str(len(key_phrases_response.get('KeyPhrases', []))),
                'analysis-type': 'synchronous'
            }
        )

        logger.info(f"Analysis completed and saved to: s3://{BUCKET_NAME}/{output_key}")
        logger.info(f"Sentiment: {sentiment_response.get('Sentiment')}")
        logger.info(f"Entities found: {len(entities_response.get('Entities', []))}")
        logger.info(f"Key phrases found: {len(key_phrases_response.get('KeyPhrases', []))}")

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Synchronous analysis completed successfully',
                'analysisId': analysis_id,
                'outputLocation': f's3://{BUCKET_NAME}/{output_key}',
                'sentiment': sentiment_response.get('Sentiment'),
                'entityCount': len(entities_response.get('Entities', [])),
                'keyPhraseCount': len(key_phrases_response.get('KeyPhrases', []))
            })
        }

    except Exception as e:
        logger.error(f"Synchronous analysis failed: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Synchronous analysis failed: {str(e)}'})
        }


def process_asynchronous_analysis(text, analysis_id, transcription_key, bucket_name):
    """
    Process text using asynchronous Comprehend APIs.

    Args:
        text: The transcript text to analyze
        analysis_id: Unique identifier for this analysis
        transcription_key: S3 key of the transcription file
        bucket_name: S3 bucket name

    Returns:
        dict: Response with status code and message
    """
    try:
        logger.info("Starting asynchronous Comprehend analysis...")

        # Save text to S3 for async processing
        input_key = f"comprehend-input/{analysis_id}.txt"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=input_key,
            Body=text.encode('utf-8'),
            ContentType='text/plain'
        )
        logger.info(f"Saved input text to: s3://{BUCKET_NAME}/{input_key}")

        input_s3_uri = f"s3://{BUCKET_NAME}/{input_key}"
        output_s3_uri = f"s3://{BUCKET_NAME}/comprehend-output/{analysis_id}/"

        job_ids = {}

        # Start sentiment detection job
        try:
            sentiment_job_name = f"sentiment-{analysis_id}"
            sentiment_response = comprehend_client.start_sentiment_detection_job(
                InputDataConfig={
                    'S3Uri': input_s3_uri,
                    'InputFormat': 'ONE_DOC_PER_FILE'
                },
                OutputDataConfig={
                    'S3Uri': output_s3_uri
                },
                DataAccessRoleArn=COMPREHEND_ROLE_ARN,
                JobName=sentiment_job_name,
                LanguageCode=LANGUAGE_CODE.split('-')[0]  # Use 'en' instead of 'en-US'
            )
            job_ids['sentiment'] = sentiment_response['JobId']
            logger.info(f"Started sentiment job: {sentiment_job_name} (ID: {sentiment_response['JobId']})")
        except Exception as e:
            logger.error(f"Failed to start sentiment job: {e}")

        # Start entities detection job
        try:
            entities_job_name = f"entities-{analysis_id}"
            entities_response = comprehend_client.start_entities_detection_job(
                InputDataConfig={
                    'S3Uri': input_s3_uri,
                    'InputFormat': 'ONE_DOC_PER_FILE'
                },
                OutputDataConfig={
                    'S3Uri': output_s3_uri
                },
                DataAccessRoleArn=COMPREHEND_ROLE_ARN,
                JobName=entities_job_name,
                LanguageCode=LANGUAGE_CODE.split('-')[0]
            )
            job_ids['entities'] = entities_response['JobId']
            logger.info(f"Started entities job: {entities_job_name} (ID: {entities_response['JobId']})")
        except Exception as e:
            logger.error(f"Failed to start entities job: {e}")

        # Start key phrases detection job
        try:
            key_phrases_job_name = f"key-phrases-{analysis_id}"
            key_phrases_response = comprehend_client.start_key_phrases_detection_job(
                InputDataConfig={
                    'S3Uri': input_s3_uri,
                    'InputFormat': 'ONE_DOC_PER_FILE'
                },
                OutputDataConfig={
                    'S3Uri': output_s3_uri
                },
                DataAccessRoleArn=COMPREHEND_ROLE_ARN,
                JobName=key_phrases_job_name,
                LanguageCode=LANGUAGE_CODE.split('-')[0]
            )
            job_ids['keyPhrases'] = key_phrases_response['JobId']
            logger.info(f"Started key phrases job: {key_phrases_job_name} (ID: {key_phrases_response['JobId']})")
        except Exception as e:
            logger.error(f"Failed to start key phrases job: {e}")

        # Save metadata about the async jobs
        async_metadata = {
            'analysisId': analysis_id,
            'transcriptionFile': f's3://{bucket_name}/{transcription_key}',
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'analysisType': 'asynchronous',
            'textLength': len(text),
            'textBytes': len(text.encode('utf-8')),
            'inputLocation': input_s3_uri,
            'outputLocation': output_s3_uri,
            'jobIds': job_ids,
            'status': 'IN_PROGRESS'
        }

        metadata_key = f"{SENTIMENT_PREFIX}{analysis_id}-metadata.json"
        s3_client.put_object(
            Bucket=BUCKET_NAME,
            Key=metadata_key,
            Body=json.dumps(async_metadata, indent=2),
            ContentType='application/json'
        )

        logger.info(f"Async jobs started. Metadata saved to: s3://{BUCKET_NAME}/{metadata_key}")
        logger.info(f"Jobs will be processed by ComprehendJobCompletionFunction when complete")

        return {
            'statusCode': 202,
            'body': json.dumps({
                'message': 'Asynchronous analysis jobs started successfully',
                'analysisId': analysis_id,
                'jobIds': job_ids,
                'metadataLocation': f's3://{BUCKET_NAME}/{metadata_key}',
                'status': 'IN_PROGRESS'
            })
        }

    except Exception as e:
        logger.error(f"Asynchronous analysis failed: {e}", exc_info=True)
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Asynchronous analysis failed: {str(e)}'})
        }
