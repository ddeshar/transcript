from __future__ import annotations

import asyncio
from typing import Optional

import boto3
from botocore.exceptions import NoCredentialsError, ClientError

from .mt_base import MTProvider, MTResult
from ..utils import to_thread


class AWSTranslateProvider(MTProvider):
    name = "awstranslate"

    def __init__(
        self,
        region_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None
    ) -> None:
        self.region_name = region_name or "us-east-1"
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self._client = None
        self._lock = asyncio.Lock()

    async def setup(self) -> None:
        async with self._lock:
            if self._client is None:
                try:
                    # Get credentials from environment if not provided
                    if not self.aws_access_key_id or not self.aws_secret_access_key:
                        from ..utils import get_env
                        self.aws_access_key_id = get_env("AWS_ACCESS_KEY_ID")
                        self.aws_secret_access_key = get_env("AWS_SECRET_ACCESS_KEY")
                        self.region_name = get_env("AWS_REGION", self.region_name)
                    
                    if not self.aws_access_key_id or not self.aws_secret_access_key:
                        raise RuntimeError(
                            "AWS credentials not found. Please set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY environment variables."
                        )
                    
                    # Create AWS session with explicit credentials
                    session = boto3.Session(
                        aws_access_key_id=self.aws_access_key_id,
                        aws_secret_access_key=self.aws_secret_access_key,
                        region_name=self.region_name
                    )
                    
                    self._client = session.client("translate")
                    
                    # Test the credentials by making a simple call
                    await to_thread(self._test_credentials)
                    
                except NoCredentialsError:
                    raise RuntimeError(
                        "AWS credentials not configured. Please set up AWS credentials via environment variables."
                    )
                except ClientError as e:
                    error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                    if error_code == 'UnauthorizedOperation':
                        raise RuntimeError(
                            "AWS credentials are invalid or do not have permission to access AWS Translate service."
                        )
                    else:
                        raise RuntimeError(f"AWS Translate setup failed: {e}")
                except Exception as e:
                    raise RuntimeError(f"Failed to initialize AWS Translate: {e}")

    async def _test_credentials(self):
        """Test AWS credentials with a minimal API call"""
        try:
            # Test with very short text to minimize cost
            self._client.translate_text(
                Text="Hi",
                SourceLanguageCode="en",
                TargetLanguageCode="th",
            )
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == 'AccessDeniedException':
                raise RuntimeError(
                    "AWS credentials do not have permission for AWS Translate. Please add 'translate:TranslateText' permission."
                )
            raise

    async def translate(self, text: str, *, is_final: bool) -> MTResult:
        if not text.strip():
            return MTResult(text="", provider=self.name, is_final=is_final)
        
        if self._client is None:
            raise RuntimeError("AWSTranslateProvider.setup() must be awaited before use.")
        
        try:
            response = await to_thread(
                self._client.translate_text,
                Text=text,
                SourceLanguageCode="en",
                TargetLanguageCode="th",
            )
            thai = response.get("TranslatedText", "").strip()
            return MTResult(text=thai, provider=self.name, is_final=is_final, raw=response)
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_msg = e.response.get('Error', {}).get('Message', str(e))
            
            if error_code == 'ThrottlingException':
                # Return original text if rate limited
                print(f"AWS Translate rate limit exceeded: {error_msg}")
                return MTResult(text=text, provider=self.name, is_final=is_final, raw={"error": "rate_limit"})
            elif error_code == 'TextSizeLimitExceededException':
                # Text too long, try to truncate
                truncated_text = text[:5000]  # AWS Translate limit is 5000 bytes
                try:
                    response = await to_thread(
                        self._client.translate_text,
                        Text=truncated_text,
                        SourceLanguageCode="en",
                        TargetLanguageCode="th",
                    )
                    thai = response.get("TranslatedText", "").strip()
                    return MTResult(text=thai, provider=self.name, is_final=is_final, raw=response)
                except Exception:
                    return MTResult(text=text, provider=self.name, is_final=is_final, raw={"error": "text_too_long"})
            else:
                print(f"AWS Translate error ({error_code}): {error_msg}")
                return MTResult(text=text, provider=self.name, is_final=is_final, raw={"error": error_code})
        
        except Exception as e:
            print(f"AWS Translate unexpected error: {e}")
            return MTResult(text=text, provider=self.name, is_final=is_final, raw={"error": str(e)})


__all__ = ["AWSTranslateProvider"]
