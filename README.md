# Yerttle Tours - AWS Transcription & Analysis Service

AWS backend service for the Yerttle Tours iOS app that automatically transcribes m4a audio files uploaded to S3 using AWS Transcribe, then analyzes the transcripts using AWS Comprehend for sentiment analysis, entity detection, and key phrase extraction.

## Architecture

This service uses a serverless, event-driven architecture:

### Transcription Pipeline
1. **Audio Upload**: iOS app uploads m4a files to the `yerttle-tours` S3 bucket
2. **Event Detection**: EventBridge detects new m4a file uploads
3. **Start Transcription**: `StartTranscriptionFunction` Lambda initiates AWS Transcribe job
4. **Transcription Processing**: AWS Transcribe processes audio asynchronously
5. **Job Completion**: EventBridge detects transcription job completion
6. **Results Processing**: `ProcessTranscriptionFunction` Lambda logs results and validates output
7. **Storage**: Transcription JSON files (with timestamps) saved to `transcriptions/` folder

### Comprehend Analysis Pipeline
8. **Analysis Trigger**: EventBridge detects new transcription JSON creation
9. **Text Analysis**: `SentimentAnalysisFunction` Lambda reads transcript and determines processing method:
   - **Small texts (<5KB)**: Synchronous API for immediate results
   - **Large texts (≥5KB)**: Asynchronous jobs for scalability
10. **Comprehend Processing**: AWS Comprehend performs three analyses:
    - **Sentiment Analysis**: Positive/Negative/Neutral/Mixed with confidence scores
    - **Entity Detection**: People, places, organizations, dates, etc.
    - **Key Phrase Extraction**: Important phrases and topics
11. **Results Compilation**: `ComprehendJobCompletionFunction` (for async jobs) aggregates all results
12. **Storage**: Analysis JSON files saved to `sentiment/` folder in same S3 bucket

## Project Structure

```
yerttle-create-aws/
├── template.yaml                          # SAM template defining infrastructure
├── samconfig.toml                         # SAM CLI configuration
├── src/
│   ├── start_transcription/
│   │   ├── app.py                        # Lambda: Start transcription job
│   │   └── requirements.txt               # Python dependencies
│   ├── process_transcription/
│   │   ├── app.py                        # Lambda: Process completed transcription
│   │   └── requirements.txt               # Python dependencies
│   ├── sentiment_analysis/
│   │   ├── app.py                        # Lambda: Analyze transcript with Comprehend
│   │   └── requirements.txt               # Python dependencies
│   └── comprehend_job_completion/
│       ├── app.py                        # Lambda: Process async Comprehend results
│       └── requirements.txt               # Python dependencies
└── README.md                              # This file
```

## Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** configured with credentials
   ```bash
   aws configure
   ```
3. **AWS SAM CLI** installed
   ```bash
   brew install aws-sam-cli  # macOS
   # or follow: https://docs.aws.amazon.com/serverless-application-model/latest/developerguide/install-sam-cli.html
   ```
4. **Python 3.10** or later
5. **S3 Bucket** named `yerttle-tours` (or update BUCKET_NAME in template.yaml)
6. **EventBridge enabled on S3 bucket**:
   ```bash
   aws s3api put-bucket-notification-configuration \
     --bucket yerttle-tours \
     --notification-configuration '{
       "EventBridgeConfiguration": {}
     }'
   ```

## Deployment

### First-Time Deployment

1. **Clone the repository**
   ```bash
   cd /path/to/yerttle-create-aws
   ```

2. **Build the SAM application**
   ```bash
   sam build
   ```

3. **Deploy with guided setup**
   ```bash
   sam deploy --guided
   ```

   During guided deployment, you'll be prompted for:
   - Stack name (default: `yerttle-transcription-stack`)
   - AWS Region (should match your S3 bucket region)
   - Confirm IAM role creation: Yes
   - Allow SAM CLI IAM role creation: Yes
   - Save arguments to configuration file: Yes

4. **Verify deployment**
   ```bash
   aws cloudformation describe-stacks --stack-name yerttle-transcription-stack
   ```

### Subsequent Deployments

After the first deployment, use the simplified command:

```bash
sam build && sam deploy
```

## Usage

### Upload Audio File

Upload an m4a file to the S3 bucket (from iOS app or CLI):

```bash
aws s3 cp /path/to/audio.m4a s3://yerttle-tours/audio.m4a
```

### Monitor Transcription

1. **Check Lambda logs** (Start Transcription):
   ```bash
   sam logs -n StartTranscriptionFunction --tail
   ```

2. **Check Lambda logs** (Process Transcription):
   ```bash
   sam logs -n ProcessTranscriptionFunction --tail
   ```

3. **View CloudWatch logs**:
   ```bash
   aws logs tail /aws/lambda/yerttle-start-transcription --follow
   aws logs tail /aws/lambda/yerttle-process-transcription --follow
   ```

4. **Check transcription job status**:
   ```bash
   aws transcribe list-transcription-jobs --status COMPLETED --max-results 5
   ```

### Retrieve Transcription

Download the transcription JSON file:

```bash
aws s3 cp s3://yerttle-tours/transcriptions/[filename].json ./
```

The JSON file includes:
- Full transcript text
- Word-level timestamps
- Confidence scores for each word
- Audio segment information

### Monitor Comprehend Analysis

1. **Check Lambda logs** (Sentiment Analysis):
   ```bash
   sam logs -n SentimentAnalysisFunction --tail
   ```

2. **Check Lambda logs** (Job Completion):
   ```bash
   sam logs -n ComprehendJobCompletionFunction --tail
   ```

3. **View CloudWatch logs**:
   ```bash
   aws logs tail /aws/lambda/yerttle-sentiment-analysis --follow
   aws logs tail /aws/lambda/yerttle-comprehend-job-completion --follow
   ```

4. **Check Comprehend job status** (for async jobs):
   ```bash
   aws comprehend list-sentiment-detection-jobs --filter Status=COMPLETED --max-results 5
   aws comprehend list-entities-detection-jobs --filter Status=COMPLETED --max-results 5
   aws comprehend list-key-phrases-detection-jobs --filter Status=COMPLETED --max-results 5
   ```

### Retrieve Analysis Results

Download the analysis JSON file:

```bash
aws s3 cp s3://yerttle-tours/sentiment/[filename]-analysis.json ./
```

The analysis JSON file includes:

#### For Synchronous Processing (<5KB transcripts):
```json
{
  "analysisId": "audio-20241028-120000",
  "analysisType": "synchronous",
  "sentiment": {
    "Sentiment": "POSITIVE",
    "SentimentScore": {
      "Positive": 0.95,
      "Negative": 0.01,
      "Neutral": 0.03,
      "Mixed": 0.01
    }
  },
  "entities": {
    "Entities": [
      {
        "Text": "San Francisco",
        "Type": "LOCATION",
        "Score": 0.99,
        "BeginOffset": 23,
        "EndOffset": 36
      }
    ],
    "Count": 15
  },
  "keyPhrases": {
    "KeyPhrases": [
      {
        "Text": "beautiful day",
        "Score": 0.98,
        "BeginOffset": 10,
        "EndOffset": 23
      }
    ],
    "Count": 8
  }
}
```

#### For Asynchronous Processing (≥5KB transcripts):
Results are aggregated from three separate Comprehend jobs and saved with the same structure.

## Configuration

### Environment Variables

Modify in `template.yaml` under `Globals.Function.Environment.Variables`:

- `BUCKET_NAME`: S3 bucket name (default: `yerttle-tours`)
- `LANGUAGE_CODE`: Language for transcription and analysis (default: `en-US`)
- `TRANSCRIPTION_PREFIX`: S3 prefix for transcription output (default: `transcriptions/`)
- `SENTIMENT_PREFIX`: S3 prefix for analysis output (default: `sentiment/`)

### Transcription Settings

Modify in `src/start_transcription/app.py` in the `start_transcription_job` call:

- `MediaFormat`: Audio format (default: `m4a`)
- `ShowSpeakerLabels`: Enable speaker identification (default: `False`)
- `MaxSpeakerLabels`: Maximum number of speakers (default: `2`)

## Cost Considerations

### Per Transcription Costs (5-minute audio):
- **AWS Transcribe**: $0.024/min × 5 min = **$0.12**
- **AWS Comprehend**:
  - Sentiment Analysis: ~$0.0008 (750 characters)
  - Entity Detection: ~$0.0008 (750 characters)
  - Key Phrase Extraction: ~$0.0008 (750 characters)
  - **Total: ~$0.0024**
- **Lambda**: ~4 invocations = negligible (within free tier)
- **S3**: Storage + requests = negligible
- **EventBridge**: Free for AWS service events

**Total per audio file: ~$0.12**

### Free Tier Benefits:
- **AWS Transcribe**: 60 minutes free per month (first 12 months)
- **AWS Comprehend**: 50,000 units (5M characters) free per month (first 12 months)
- **Lambda**: 1M requests + 400,000 GB-seconds free per month (always)

### Monthly Costs (100 5-minute transcriptions):
- AWS Transcribe: $12.00
- AWS Comprehend: $0.24
- Lambda/S3/EventBridge: <$1.00
- **Total: ~$13.24/month**

### Cost Optimization:
- Comprehend synchronous API (<5KB): Most cost-effective for short transcripts
- Comprehend async API (≥5KB): Better for large transcripts but same pricing
- All services have generous free tiers for first 12 months

## Troubleshooting

### Lambda Function Not Triggering

1. Verify EventBridge is enabled on S3 bucket
2. Check CloudWatch logs for errors
3. Verify IAM permissions in Lambda execution role

### Transcription Job Fails

1. Check audio file format is supported m4a
2. Verify S3 bucket permissions
3. Check CloudWatch logs for specific error messages
4. Ensure audio file size is within AWS Transcribe limits (< 2GB for async jobs)

### No Output in S3

1. Verify transcription job completed successfully
2. Check S3 bucket permissions for Lambda function
3. Review ProcessTranscriptionFunction logs

### Comprehend Analysis Not Running

1. Verify EventBridge is detecting transcription JSON files
2. Check SentimentAnalysisFunction CloudWatch logs for errors
3. Verify IAM permissions include Comprehend actions
4. Ensure ComprehendServiceRole has S3 read/write permissions
5. Check that COMPREHEND_ROLE_ARN environment variable is set

### Async Comprehend Jobs Failing

1. Verify ComprehendServiceRole can access S3 bucket
2. Check Comprehend job status in AWS Console or CLI
3. Ensure text is properly formatted (UTF-8 encoding)
4. Review ComprehendJobCompletionFunction logs
5. Verify IAM PassRole permission exists for Lambda to use ComprehendServiceRole

### No Comprehend Results in S3

1. Check if analysis completed (look for *-analysis.json file)
2. For async jobs: Verify all three jobs (sentiment, entities, key phrases) completed
3. Review ComprehendJobCompletionFunction logs for aggregation errors
4. Check S3 bucket permissions for sentiment/ prefix

## Development

### Local Testing

```bash
# Invoke function locally
sam local invoke StartTranscriptionFunction -e events/s3-event.json

# Start API Gateway locally
sam local start-api
```

### Run Tests

```bash
python -m pytest tests/
```

## Cleanup

To delete all AWS resources created by this stack:

```bash
sam delete
```

This will remove:
- Lambda functions (4 total: transcription start/process + sentiment analysis + job completion)
- IAM roles (Lambda execution roles + ComprehendServiceRole)
- EventBridge rules (S3 events + Transcribe events + Comprehend events)
- CloudWatch log groups

Note: The S3 bucket `yerttle-tours` and its contents (audio files, transcriptions, analysis results) are NOT deleted. You may want to manually clean up:
- `transcriptions/` folder
- `sentiment/` folder
- `comprehend-input/` folder (for async jobs)
- `comprehend-output/` folder (for async jobs)

## Support

For issues or questions:
- Check CloudWatch logs for detailed error messages
- Review AWS Transcribe documentation: https://docs.aws.amazon.com/transcribe/
- Review AWS Comprehend documentation: https://docs.aws.amazon.com/comprehend/
- Review AWS SAM documentation: https://docs.aws.amazon.com/serverless-application-model/

## License

[Specify your license here]