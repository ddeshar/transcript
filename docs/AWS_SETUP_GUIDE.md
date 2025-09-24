# AWS Integration Setup Guide

This guide will help you set up AWS services for your English-Thai subtitle application. AWS integration provides high-quality machine translation through AWS Translate service.

## 🚀 Quick Setup Overview

1. **Create AWS Account** → Get AWS credentials
2. **Set up IAM User** → Create user with translation permissions  
3. **Configure Application** → Add credentials to environment variables
4. **Test Integration** → Verify everything works

---

## 📋 Detailed Setup Steps

### Step 1: Create AWS Account

If you don't have an AWS account:
1. Go to [https://aws.amazon.com/](https://aws.amazon.com/)
2. Click "Create an AWS Account"
3. Follow the registration process (requires credit card, but we'll use free tier)

### Step 2: Create IAM User with Translation Permissions

**Why IAM User?** For security, don't use your root AWS account. Create a dedicated user with minimal permissions.

1. **Sign in to AWS Console**
   - Go to [https://console.aws.amazon.com/](https://console.aws.amazon.com/)
   - Sign in with your AWS account

2. **Navigate to IAM Service**
   - In the AWS Console search bar, type "IAM" and click on it
   - Or go directly to [https://console.aws.amazon.com/iam/](https://console.aws.amazon.com/iam/)

3. **Create New User**
   - Click "Users" in the left sidebar
   - Click "Create user" button
   - Enter username: `transcript-app-user` (or any name you prefer)
   - Select "Programmatic access" (we need API keys, not console access)
   - Click "Next"

4. **Set Permissions**
   - Choose "Attach policies directly"
   - Search for "TranslateReadOnly" and select it
   - **IMPORTANT**: Also create a custom policy for translate permissions:
     
     **Option A: Use AWS Managed Policy (Easier)**
     - Search for "TranslateFullAccess" and select it
     
     **Option B: Create Custom Policy (More Secure - Recommended)**
     - Click "Create policy"
     - Choose "JSON" tab and paste:
     ```json
     {
         "Version": "2012-10-17",
         "Statement": [
             {
                 "Effect": "Allow",
                 "Action": [
                     "translate:TranslateText",
                     "translate:GetTerminology",
                     "translate:ListTerminologies"
                 ],
                 "Resource": "*"
             }
         ]
     }
     ```
     - Click "Next", name it `TranscriptAppTranslatePolicy`
     - Click "Create policy"
     - Go back to user creation and attach this policy

5. **Complete User Creation**
   - Review settings and click "Create user"
   - **IMPORTANT**: Copy and save the credentials:
     - **Access Key ID** (starts with AKIA...)
     - **Secret Access Key** (long random string)
   - ⚠️ **You won't be able to see the Secret Access Key again!**

### Step 3: Configure Your Application

#### Option A: Using the Settings Interface (Recommended)
1. Start your application:
   ```bash
   docker-compose up --build
   ```
2. Open [http://localhost:8000/settings](http://localhost:8000/settings)
3. Scroll to the "AWS" section
4. Fill in:
   - **AWS_REGION**: `us-east-1` (or your preferred region)
   - **AWS_ACCESS_KEY_ID**: Your Access Key ID from Step 2
   - **AWS_SECRET_ACCESS_KEY**: Your Secret Access Key from Step 2
5. Click "Save Settings"

#### Option B: Edit Environment File Manually
1. Edit `.env.docker` file:
   ```bash
   # AWS Configuration
   AWS_REGION=us-east-1
   AWS_ACCESS_KEY_ID=AKIA1234567890EXAMPLE
   AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
   ```
2. Rebuild and restart:
   ```bash
   docker-compose up --build
   ```

#### Option C: Using AWS CLI (Advanced)
If you have AWS CLI installed:
```bash
aws configure
# Enter your Access Key ID and Secret Access Key
# Choose region: us-east-1
# Output format: json
```

### Step 4: Switch to AWS Translate

1. **Via Settings Interface**:
   - Go to [http://localhost:8000/settings](http://localhost:8000/settings)
   - In the "Providers" section, set **MT_PROVIDER** to `awstranslate`
   - Click "Save Settings"

2. **Via Environment File**:
   ```bash
   # Edit .env.docker
   MT_PROVIDER=awstranslate
   ```

3. **Restart Application**:
   ```bash
   docker-compose restart
   ```

---

## 🧪 Testing Your Setup

### Test 1: Basic Connection
1. Open your application at [http://localhost:8000](http://localhost:8000)
2. Speak some English
3. Check if Thai translation appears
4. Look at logs: `docker-compose logs -f`

### Test 2: Manual API Test
You can test AWS Translate directly using AWS CLI:
```bash
aws translate translate-text \
    --source-language-code "en" \
    --target-language-code "th" \
    --text "Hello, how are you?" \
    --region us-east-1
```

Expected output:
```json
{
    "TranslatedText": "สวัสดี คุณเป็นอย่างไรบ้าง?",
    "SourceLanguageCode": "en",
    "TargetLanguageCode": "th"
}
```

---

## 💰 Cost Information

### AWS Translate Pricing (as of 2024)
- **Free Tier**: 2 million characters per month for 12 months
- **Pay-as-you-go**: $15.00 per 1 million characters
- **Character count**: Includes spaces and punctuation

### Estimated Costs for Subtitle App:
- **Light usage** (1 hour/day): ~$3-5/month
- **Heavy usage** (8 hours/day): ~$20-30/month
- **Continuous use**: ~$100-150/month

**💡 Tip**: Start with free tier to test, monitor usage in AWS billing dashboard.

---

## 🔧 Troubleshooting

### Common Issues

#### ❌ Error: "AWS credentials not found"
**Solution**: 
- Check that AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY are set
- Verify no typos in credentials
- Restart application after setting credentials

#### ❌ Error: "AWS credentials are invalid"  
**Solution**:
- Verify credentials are correct (re-check Access Key ID and Secret)
- Ensure IAM user has translate permissions
- Check if credentials are active (not deleted)

#### ❌ Error: "do not have permission for AWS Translate"
**Solution**:
- Go to IAM console → Users → your user → Permissions
- Attach "TranslateFullAccess" policy or custom translate policy
- Wait 5-10 minutes for permissions to propagate

#### ❌ Error: "Rate limit exceeded"
**Solution**:
- AWS has rate limits (100 requests/second by default)  
- Reduce audio chunk frequency if needed
- Consider upgrading AWS limits if required

#### ❌ Translation appears as English text
**Solution**:
- Check MT_PROVIDER is set to "awstranslate"
- Verify AWS Translate is working with manual test
- Check application logs for AWS errors

### Regional Considerations

AWS Translate is available in these regions:
- `us-east-1` (N. Virginia) - **Recommended**
- `us-west-2` (Oregon)
- `eu-west-1` (Ireland)
- `ap-southeast-2` (Sydney)

Choose the region closest to your location for better latency.

---

## 🔒 Security Best Practices

### 🚨 Important Security Notes

1. **Never commit credentials to git**:
   ```bash
   # Add to .gitignore
   .env.docker
   .env
   ```

2. **Use environment variables only**:
   - Don't hardcode keys in source code
   - Use Docker secrets in production

3. **Rotate keys regularly**:
   - Generate new Access Keys every 90 days
   - Delete old keys from IAM

4. **Monitor usage**:
   - Set up AWS billing alerts
   - Check CloudTrail for API usage
   - Monitor for unusual activity

### Production Deployment

For production, consider:
- **AWS IAM Roles** instead of Access Keys (for EC2/ECS)
- **AWS Secrets Manager** for credential storage
- **VPC endpoints** for private API access
- **CloudWatch** for monitoring and alerting

---

## 🌟 Next Steps

After successful setup:

1. **Compare Translation Quality**:
   - Test AWS Translate vs other providers (OpenAI GPT, Google Translate)
   - AWS excels at business/formal text
   - OpenAI GPT better for conversational/colloquial text

2. **Optimize Performance**:
   - AWS Translate is typically faster than OpenAI API
   - Consider hybrid approach: fast local English + AWS Thai translation

3. **Monitor Costs**:
   - Set up AWS billing alerts
   - Track character usage
   - Consider batch processing for cost optimization

4. **Advanced Features**:
   - Custom terminologies for domain-specific translation
   - Language detection for multi-language support
   - Real-time streaming with AWS Transcribe + Translate

---

## 📞 Support

If you encounter issues:

1. **Check Application Logs**:
   ```bash
   docker-compose logs -f
   ```

2. **Verify AWS Status**:
   - [AWS Service Health](https://status.aws.amazon.com/)
   - Check your specific region

3. **AWS Support**:
   - AWS documentation: [AWS Translate Developer Guide](https://docs.aws.amazon.com/translate/)
   - AWS forums: [AWS re:Post](https://repost.aws/)

4. **Application Support**:
   - Check GitHub issues
   - Review configuration files
   - Test with simple providers first (e.g., simple_thai)

---

## ✅ Quick Checklist

Before going live with AWS integration:

- [ ] AWS account created
- [ ] IAM user created with translate permissions
- [ ] Access Key ID and Secret Access Key saved securely
- [ ] Credentials added to application environment
- [ ] MT_PROVIDER set to "awstranslate"  
- [ ] Application restarted
- [ ] Basic translation test successful
- [ ] Billing alerts configured
- [ ] Credentials secured (not in git)
- [ ] Backup authentication method available

**🎉 You're all set! Enjoy high-quality AWS-powered Thai translations!**