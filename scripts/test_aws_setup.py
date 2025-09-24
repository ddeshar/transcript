#!/usr/bin/env python3
"""
AWS Setup Test Script for Transcript Application

This script helps you test your AWS configuration before using it in the application.
Run this script to verify your AWS credentials and permissions are set up correctly.
"""

import os
import sys
from pathlib import Path

def test_aws_import():
    """Test if boto3 is installed"""
    try:
        import boto3
        from botocore.exceptions import NoCredentialsError, ClientError
        print("✅ boto3 library found")
        return True, boto3, NoCredentialsError, ClientError
    except ImportError as e:
        print(f"❌ boto3 not installed: {e}")
        print("Install with: pip install boto3")
        return False, None, None, None

def load_env_file():
    """Load environment variables from .env.docker"""
    env_file = Path(__file__).parent.parent / ".env.docker"
    env_vars = {}
    
    if not env_file.exists():
        print(f"⚠️  Environment file not found: {env_file}")
        return env_vars
    
    try:
        with open(env_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    
                    # Remove quotes if present
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    
                    env_vars[key] = value
        
        print(f"✅ Loaded environment from {env_file}")
        return env_vars
    except Exception as e:
        print(f"❌ Error reading environment file: {e}")
        return env_vars

def check_credentials(env_vars):
    """Check if AWS credentials are available"""
    # Check environment file
    access_key = env_vars.get('AWS_ACCESS_KEY_ID') or os.getenv('AWS_ACCESS_KEY_ID')
    secret_key = env_vars.get('AWS_SECRET_ACCESS_KEY') or os.getenv('AWS_SECRET_ACCESS_KEY')
    region = env_vars.get('AWS_REGION') or os.getenv('AWS_REGION', 'us-east-1')
    
    if not access_key:
        print("❌ AWS_ACCESS_KEY_ID not found in environment or .env.docker")
        return None
    
    if not secret_key:
        print("❌ AWS_SECRET_ACCESS_KEY not found in environment or .env.docker")
        return None
    
    # Hide most of the secret key for security
    masked_secret = secret_key[:4] + '*' * (len(secret_key) - 8) + secret_key[-4:] if len(secret_key) > 8 else '*' * len(secret_key)
    
    print("✅ AWS credentials found:")
    print(f"   Access Key ID: {access_key}")
    print(f"   Secret Key: {masked_secret}")
    print(f"   Region: {region}")
    
    return {
        'aws_access_key_id': access_key,
        'aws_secret_access_key': secret_key,
        'region_name': region
    }

def test_aws_connection(boto3, NoCredentialsError, ClientError, creds):
    """Test AWS connection and permissions"""
    if not creds:
        return False
    
    try:
        # Create AWS session
        session = boto3.Session(
            aws_access_key_id=creds['aws_access_key_id'],
            aws_secret_access_key=creds['aws_secret_access_key'],
            region_name=creds['region_name']
        )
        
        # Test STS (Security Token Service) - basic auth test
        sts_client = session.client('sts')
        identity = sts_client.get_caller_identity()
        
        print("✅ AWS authentication successful:")
        print(f"   User ARN: {identity.get('Arn', 'Unknown')}")
        print(f"   Account ID: {identity.get('Account', 'Unknown')}")
        
        return session
        
    except NoCredentialsError:
        print("❌ AWS credentials not found or invalid")
        return None
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        print(f"❌ AWS authentication failed ({error_code}): {error_msg}")
        return None
    except Exception as e:
        print(f"❌ Unexpected AWS error: {e}")
        return None

def test_translate_service(session, ClientError):
    """Test AWS Translate service access and permissions"""
    if not session:
        return False
    
    try:
        translate_client = session.client('translate')
        
        # Test with a simple translation
        print("\n🧪 Testing AWS Translate service...")
        
        response = translate_client.translate_text(
            Text="Hello",
            SourceLanguageCode="en", 
            TargetLanguageCode="th"
        )
        
        thai_text = response.get('TranslatedText', '')
        
        print("✅ AWS Translate test successful:")
        print(f"   English: Hello")
        print(f"   Thai: {thai_text}")
        print(f"   Source Language: {response.get('SourceLanguageCode', 'Unknown')}")
        print(f"   Target Language: {response.get('TargetLanguageCode', 'Unknown')}")
        
        return True
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        
        if error_code == 'AccessDeniedException':
            print("❌ AWS Translate access denied:")
            print("   Your AWS user doesn't have permission to use AWS Translate")
            print("   Please add 'translate:TranslateText' permission to your IAM user")
            print("   See AWS Setup Guide for detailed instructions")
        else:
            print(f"❌ AWS Translate error ({error_code}): {error_msg}")
        
        return False
        
    except Exception as e:
        print(f"❌ Unexpected Translate error: {e}")
        return False

def main():
    """Main test function"""
    print("🔧 AWS Configuration Test for Transcript Application")
    print("=" * 60)
    
    # Test 1: Check if boto3 is available
    print("\n1. Testing AWS SDK availability...")
    success, boto3, NoCredentialsError, ClientError = test_aws_import()
    if not success:
        print("\n❌ Setup incomplete. Please install boto3 first.")
        sys.exit(1)
    
    # Test 2: Load environment variables
    print("\n2. Loading environment configuration...")
    env_vars = load_env_file()
    
    # Test 3: Check credentials
    print("\n3. Checking AWS credentials...")
    creds = check_credentials(env_vars)
    if not creds:
        print("\n❌ AWS credentials not configured.")
        print("Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in:")
        print("  - .env.docker file, OR")
        print("  - Environment variables, OR") 
        print("  - AWS CLI configuration")
        print("\nSee AWS Setup Guide for detailed instructions.")
        sys.exit(1)
    
    # Test 4: Test AWS connection
    print("\n4. Testing AWS authentication...")
    session = test_aws_connection(boto3, NoCredentialsError, ClientError, creds)
    if not session:
        print("\n❌ AWS authentication failed.")
        print("Please check your credentials and try again.")
        sys.exit(1)
    
    # Test 5: Test Translate service
    print("\n5. Testing AWS Translate permissions...")
    translate_success = test_translate_service(session, ClientError)
    
    # Final summary
    print("\n" + "=" * 60)
    if translate_success:
        print("🎉 SUCCESS! Your AWS configuration is ready to use.")
        print("\nNext steps:")
        print("1. Set MT_PROVIDER=awstranslate in your .env.docker")
        print("2. Restart your application: docker-compose up --build")
        print("3. Test real-time translation at http://localhost:8000")
    else:
        print("⚠️  AWS authentication works, but Translate permissions need fixing.")
        print("\nTo fix:")
        print("1. Go to AWS IAM Console")
        print("2. Find your user and attach 'TranslateFullAccess' policy")
        print("3. Wait 5-10 minutes for permissions to propagate")
        print("4. Run this test again")
    
    print("\nFor detailed setup instructions, see docs/AWS_SETUP_GUIDE.md")

if __name__ == "__main__":
    main()