# GitHub Actions Workflows

This directory contains automated CI/CD workflows for the Yerttle Tours transcription service.

## Workflows

### `deploy.yml` - Automated AWS Deployment

Automatically builds and deploys the SAM application to AWS when code is pushed to the `main` branch.

**Triggers:**
- Push to `main` branch
- Manual trigger via GitHub Actions UI (workflow_dispatch)

**Steps:**
1. Checkout code
2. Set up Python 3.10
3. Install AWS SAM CLI
4. Configure AWS credentials
5. Build SAM application
6. Deploy to AWS
7. Display stack outputs

## Required GitHub Secrets

Before the workflow can run successfully, you must configure the following secrets in your GitHub repository:

### Setting Up Secrets

1. Go to your GitHub repository
2. Navigate to **Settings** → **Secrets and variables** → **Actions**
3. Click **New repository secret**
4. Add each of the following secrets:

### Required Secrets

| Secret Name | Description | Example |
|-------------|-------------|---------|
| `AWS_ACCESS_KEY_ID` | AWS access key for deployment IAM user | `AKIAIOSFODNN7EXAMPLE` |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key for deployment IAM user | `wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY` |
| `AWS_REGION` | AWS region where resources will be deployed | `us-east-1` |
| `SAM_BUCKET_NAME` | S3 bucket name for storing deployment artifacts | `yerttle-sam-deployments` |

### Creating AWS IAM User for Deployment

The IAM user needs the following permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "cloudformation:*",
        "s3:*",
        "lambda:*",
        "iam:*",
        "logs:*",
        "events:*",
        "transcribe:*",
        "comprehend:*"
      ],
      "Resource": "*"
    }
  ]
}
```

**Security Best Practice:** Create a dedicated IAM user specifically for CI/CD deployments with minimal required permissions.

### Creating S3 Bucket for SAM Artifacts

The S3 bucket must exist before the first deployment:

```bash
# Create the bucket (replace with your bucket name and region)
aws s3 mb s3://yerttle-sam-deployments --region us-east-1

# Enable versioning (recommended)
aws s3api put-bucket-versioning \
  --bucket yerttle-sam-deployments \
  --versioning-configuration Status=Enabled

# Add lifecycle policy to clean up old artifacts (optional)
aws s3api put-bucket-lifecycle-configuration \
  --bucket yerttle-sam-deployments \
  --lifecycle-configuration '{
    "Rules": [{
      "Id": "DeleteOldArtifacts",
      "Status": "Enabled",
      "Prefix": "yerttle-transcription/",
      "NoncurrentVersionExpiration": {
        "NoncurrentDays": 30
      },
      "AbortIncompleteMultipartUpload": {
        "DaysAfterInitiation": 7
      }
    }]
  }'
```

## Deployment Process

### Automatic Deployment

When you push code to the `main` branch:

```bash
git add .
git commit -m "Update Lambda function"
git push origin main
```

The workflow will automatically:
1. Build the SAM application
2. Deploy to AWS
3. Display stack outputs
4. Report success/failure

### Manual Deployment

You can trigger deployment manually:

1. Go to **Actions** tab in GitHub
2. Select **Deploy to AWS** workflow
3. Click **Run workflow**
4. Select branch (typically `main`)
5. Click **Run workflow** button

## Monitoring Deployments

### View Deployment Status

1. Go to **Actions** tab in GitHub
2. Click on the latest workflow run
3. Expand each step to see detailed logs

### Check AWS Resources

After successful deployment, verify resources in AWS Console:

```bash
# List CloudFormation stacks
aws cloudformation list-stacks --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE

# Describe specific stack
aws cloudformation describe-stacks --stack-name yerttle-transcription-stack

# List Lambda functions
aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `yerttle-`)].FunctionName'

# Check EventBridge rules
aws events list-rules --name-prefix yerttle
```

## Troubleshooting

### Deployment Fails with "Access Denied"

**Problem:** IAM user lacks necessary permissions

**Solution:**
1. Check IAM user has required permissions (see above)
2. Verify AWS credentials are correct in GitHub secrets
3. Ensure S3 bucket exists and is accessible

### Deployment Fails with "Bucket Not Found"

**Problem:** S3 bucket for SAM artifacts doesn't exist

**Solution:**
```bash
aws s3 mb s3://your-bucket-name --region your-region
```

### Build Fails with "Runtime not supported"

**Problem:** SAM CLI version or Docker container issue

**Solution:**
1. Check Python version in `template.yaml` matches workflow
2. Ensure Docker is available (for containerized builds)
3. Try removing `--use-container` flag in workflow if not needed

### Stack Already Exists Error

**Problem:** CloudFormation stack name conflict

**Solution:**
1. Change `STACK_NAME` in workflow file
2. Or delete existing stack:
```bash
aws cloudformation delete-stack --stack-name yerttle-transcription-stack
```

### GitHub Actions Runner Out of Disk Space

**Problem:** `.aws-sam` build artifacts too large

**Solution:**
1. The workflow includes caching to help
2. Periodically clear caches in Actions settings
3. Consider using smaller Lambda deployment packages

## Workflow Configuration

### Modifying Stack Name

Edit `.github/workflows/deploy.yml`:

```yaml
env:
  STACK_NAME: 'your-custom-stack-name'
```

### Changing Python Version

Update both files:
1. `.github/workflows/deploy.yml` - `PYTHON_VERSION`
2. `template.yaml` - `Runtime: python3.x`

### Adding Environment-Specific Deployments

To support multiple environments (dev/staging/prod):

1. Create separate workflows for each environment
2. Use different stack names: `yerttle-transcription-{env}`
3. Set up environment-specific secrets in GitHub
4. Use GitHub Environments feature for approval gates

## Best Practices

### Branch Protection

Protect the `main` branch:
1. Go to **Settings** → **Branches**
2. Add rule for `main` branch
3. Enable "Require status checks to pass before merging"
4. Select "Deploy to AWS" workflow

### Deployment Notifications

Set up Slack/email notifications:
1. Use GitHub Actions marketplace actions for notifications
2. Add notification steps to workflow
3. Configure on success and failure

### Rollback Strategy

If deployment fails:

```bash
# View previous stack versions
aws cloudformation describe-stack-events --stack-name yerttle-transcription-stack

# Manual rollback if needed
aws cloudformation cancel-update-stack --stack-name yerttle-transcription-stack
```

Or redeploy previous working commit:
```bash
git revert HEAD
git push origin main
```

## Security Notes

- **Never commit AWS credentials** to the repository
- Rotate IAM access keys regularly
- Use least-privilege IAM policies
- Enable MFA on IAM users when possible
- Monitor CloudTrail for deployment activities
- Review GitHub Actions logs for sensitive information leaks

## Additional Resources

- [AWS SAM Documentation](https://docs.aws.amazon.com/serverless-application-model/)
- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [AWS CloudFormation](https://docs.aws.amazon.com/cloudformation/)
- [GitHub Actions for AWS](https://github.com/aws-actions)
