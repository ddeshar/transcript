from __future__ import annotations

import asyncio
import uuid
from typing import AsyncIterator, Optional
import boto3
from botocore.exceptions import NoCredentialsError, ClientError

from .asr_base import ASRProvider, ASRResult, ASRStream
from ..utils import to_thread


class AWSTranscribeStream(ASRStream):
    """AWS Transcribe streaming ASR implementation"""
    
    def __init__(self, session_id: str, transcribe_client, region_name: str, sample_rate: int) -> None:
        self.session_id = session_id
        self.transcribe_client = transcribe_client
        self.region_name = region_name
        self.sample_rate = sample_rate
        self._buffer = bytearray()
        self._queue: asyncio.Queue[Optional[ASRResult]] = asyncio.Queue()
        self._seq = 0
        self._lock = asyncio.Lock()
        self._job_name = f"transcript-{session_id}-{uuid.uuid4().hex[:8]}"
        self._s3_client = None
        self._bucket_name = "transcribe-audio-bucket"  # You'll need to create this
        
    async def setup_s3(self):
        """Setup S3 client for audio upload (AWS Transcribe requires S3 URLs)"""
        if self._s3_client is None:
            self._s3_client = boto3.client('s3', region_name=self.region_name)

    async def push_audio(self, chunk: bytes, timestamp_ms: int) -> None:
        """Accumulate audio chunks"""
        self._buffer.extend(chunk)
        
        # Process in larger chunks for better accuracy (5 seconds of audio)
        if len(self._buffer) >= self.sample_rate * 2 * 5:  # 5 seconds of 16-bit audio
            await self._process_buffer()

    async def mark_segment_end(self) -> None:
        """Process remaining audio when segment ends"""
        await self._process_buffer(is_final=True)

    async def finalize(self) -> None:
        """Finalize the stream"""
        await self._process_buffer(is_final=True)
        await self._queue.put(None)

    async def _process_buffer(self, is_final: bool = False) -> None:
        """Process accumulated audio buffer"""
        if not self._buffer or len(self._buffer) < 1600:  # At least 0.1 seconds
            return
            
        async with self._lock:
            audio_data = bytes(self._buffer)
            self._buffer.clear()
            
        try:
            # Convert PCM to WAV and upload to S3
            wav_data = await to_thread(self._pcm16_to_wav, audio_data)
            s3_key = f"audio/{self._job_name}-{self._seq}.wav"
            
            await self.setup_s3()
            
            # Upload to S3
            await to_thread(
                self._s3_client.put_object,
                Bucket=self._bucket_name,
                Key=s3_key,
                Body=wav_data,
                ContentType='audio/wav'
            )
            
            # Start transcription job
            s3_uri = f"s3://{self._bucket_name}/{s3_key}"
            job_name = f"{self._job_name}-{self._seq}"
            
            response = await to_thread(
                self.transcribe_client.start_transcription_job,
                TranscriptionJobName=job_name,
                Media={'MediaFileUri': s3_uri},
                MediaFormat='wav',
                LanguageCode='en-US',
                Settings={
                    'ShowSpeakerLabels': False,
                    'MaxSpeakerLabels': 1
                }
            )
            
            # Poll for completion (AWS Transcribe is async)
            transcript_text = await self._wait_for_transcription(job_name)
            
            if transcript_text:
                self._seq += 1
                await self._queue.put(
                    ASRResult(
                        session_id=self.session_id,
                        text=transcript_text,
                        is_final=is_final,
                        start_ms=0,
                        end_ms=0,
                        confidence=None,
                        segment_id=f"aws-transcribe-{self._seq}",
                        raw=response,
                    )
                )
            
            # Clean up S3 object
            await to_thread(
                self._s3_client.delete_object,
                Bucket=self._bucket_name,
                Key=s3_key
            )
            
        except Exception as e:
            print(f"AWS Transcribe error: {e}")
            # Fallback: return empty result
            if is_final:
                await self._queue.put(
                    ASRResult(
                        session_id=self.session_id,
                        text="",
                        is_final=True,
                        start_ms=0,
                        end_ms=0,
                        confidence=None,
                        segment_id=f"aws-transcribe-error-{self._seq}",
                        raw={"error": str(e)},
                    )
                )

    async def _wait_for_transcription(self, job_name: str) -> Optional[str]:
        """Wait for transcription job to complete and return text"""
        max_attempts = 30  # 30 seconds max wait
        attempt = 0
        
        while attempt < max_attempts:
            try:
                response = await to_thread(
                    self.transcribe_client.get_transcription_job,
                    TranscriptionJobName=job_name
                )
                
                status = response['TranscriptionJob']['TranscriptionJobStatus']
                
                if status == 'COMPLETED':
                    # Get transcript URL and fetch results
                    transcript_uri = response['TranscriptionJob']['Transcript']['TranscriptFileUri']
                    transcript_json = await to_thread(self._fetch_transcript, transcript_uri)
                    
                    if transcript_json and 'results' in transcript_json:
                        # Extract text from AWS Transcribe JSON format
                        if 'transcripts' in transcript_json['results'] and transcript_json['results']['transcripts']:
                            return transcript_json['results']['transcripts'][0].get('transcript', '').strip()
                    return ""
                    
                elif status == 'FAILED':
                    print(f"AWS Transcribe job {job_name} failed")
                    return None
                    
                # Still in progress, wait
                await asyncio.sleep(1)
                attempt += 1
                
            except Exception as e:
                print(f"Error waiting for transcription: {e}")
                return None
                
        print(f"AWS Transcribe job {job_name} timed out")
        return None

    def _fetch_transcript(self, transcript_uri: str) -> Optional[dict]:
        """Fetch transcript JSON from S3 URI"""
        import requests
        try:
            response = requests.get(transcript_uri)
            return response.json()
        except Exception as e:
            print(f"Error fetching transcript: {e}")
            return None

    def _pcm16_to_wav(self, pcm: bytes) -> bytes:
        """Convert PCM16 to WAV format"""
        import io
        import wave
        
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav:
            wav.setnchannels(1)  # Mono
            wav.setsampwidth(2)  # 16-bit
            wav.setframerate(self.sample_rate)
            wav.writeframes(pcm)
        buffer.seek(0)
        return buffer.read()

    async def results(self) -> AsyncIterator[ASRResult]:
        """Yield transcription results"""
        while True:
            item = await self._queue.get()
            if item is None:
                break
            yield item


class AWSTranscribeProvider(ASRProvider):
    """AWS Transcribe ASR Provider for real-time speech recognition"""
    
    name = "aws_transcribe"

    def __init__(
        self, 
        region_name: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        s3_bucket: Optional[str] = None
    ) -> None:
        self.region_name = region_name or "us-east-1"
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.s3_bucket = s3_bucket or "transcribe-audio-bucket"
        self._transcribe_client = None
        self._s3_client = None

    async def setup(self) -> None:
        """Initialize AWS clients"""
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
            
            # Create AWS clients
            session = boto3.Session(
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                region_name=self.region_name
            )
            
            self._transcribe_client = session.client('transcribe')
            self._s3_client = session.client('s3')
            
            # Ensure S3 bucket exists
            await self._ensure_s3_bucket()
            
        except NoCredentialsError:
            raise RuntimeError(
                "AWS credentials not configured. Please set up AWS credentials via environment variables or AWS CLI."
            )
        except Exception as e:
            raise RuntimeError(f"Failed to initialize AWS Transcribe: {e}")

    async def _ensure_s3_bucket(self) -> None:
        """Create S3 bucket if it doesn't exist"""
        try:
            await to_thread(self._s3_client.head_bucket, Bucket=self.s3_bucket)
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                # Bucket doesn't exist, create it
                try:
                    if self.region_name == 'us-east-1':
                        await to_thread(
                            self._s3_client.create_bucket,
                            Bucket=self.s3_bucket
                        )
                    else:
                        await to_thread(
                            self._s3_client.create_bucket,
                            Bucket=self.s3_bucket,
                            CreateBucketConfiguration={'LocationConstraint': self.region_name}
                        )
                    print(f"Created S3 bucket: {self.s3_bucket}")
                except ClientError as create_error:
                    print(f"Warning: Could not create S3 bucket {self.s3_bucket}: {create_error}")
                    print("Please create the S3 bucket manually or use an existing one")
            else:
                print(f"S3 bucket access error: {e}")

    async def create_stream(self, session_id: str, sample_rate: int) -> ASRStream:
        """Create a new transcription stream"""
        if self._transcribe_client is None:
            raise RuntimeError("AWSTranscribeProvider.setup() must be awaited before use.")
        
        stream = AWSTranscribeStream(
            session_id=session_id,
            transcribe_client=self._transcribe_client,
            region_name=self.region_name,
            sample_rate=sample_rate
        )
        stream._bucket_name = self.s3_bucket
        return stream


__all__ = ["AWSTranscribeProvider"]