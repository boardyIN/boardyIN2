from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional
import uuid
from datetime import datetime
import random
import time
import asyncio

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Create the main app without a prefix
app = FastAPI()

# Create a router with the /api prefix
api_router = APIRouter(prefix="/api")

# Pydantic Models
class OnboardingSession(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    customer_phone: Optional[str] = None
    customer_email: Optional[str] = None
    current_step: str = "welcome"
    progress_percentage: int = 0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = "in_progress"

class ChatMessage(BaseModel):
    session_id: str
    message: str
    sender: str  # "user" or "agent"
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class VerificationRequest(BaseModel):
    session_id: str
    phone: Optional[str] = None
    email: Optional[str] = None
    otp: Optional[str] = None
    verification_type: Optional[str] = None  # "phone" or "email"

class KYCDocumentRequest(BaseModel):
    session_id: str
    document_type: str  # "pan", "aadhaar" or "digilocker"
    pan_number: Optional[str] = None
    aadhaar_number: Optional[str] = None
    document_data: Optional[str] = None  # base64 encoded
    document_file: Optional[str] = None  # base64 encoded file

class BiometricRequest(BaseModel):
    session_id: str
    face_image: str  # base64 encoded image

class AdditionalInfoRequest(BaseModel):
    session_id: str
    full_name: str
    date_of_birth: str
    address: str
    occupation: str
    income_range: str
    
class ESignRequest(BaseModel):
    session_id: str
    signature_data: str  # base64 encoded signature

# Mock AI responses for different onboarding steps
def get_ai_response(step: str, context: dict = None) -> str:
    responses = {
        "welcome": "Hi there! I'm Boardy, your personal AI banking assistant! 👋 I'll help you complete your account opening in just a few simple steps. We'll verify your mobile number and email, then complete your KYC process. Ready to get started with me? 🚀",
        
        "phone_verification": "Great! Now I need to verify your mobile number. Please enter your 10-digit mobile number, and I'll send you an OTP for verification. 📱",
        
        "phone_otp_verification": f"Perfect! I've sent a 6-digit OTP to your mobile number. Please enter the OTP you received. (For demo: use 123456) 🔢",
        
        "email_verification": "Excellent! Now let's verify your email address. Please provide your email ID, and I'll send you a verification code. 📧",
        
        "email_otp_verification": f"Great! I've sent a 6-digit OTP to your email address. Please check your inbox and enter the OTP you received. (For demo: use 654321) 📧✨",
        
        "pan_verification": "Now let's start with your KYC verification. First, I need to verify your PAN card details. Please enter your 10-character PAN number. 🆔",
        
        "kyc_document": "Excellent! Your PAN is verified. Now please choose your preferred KYC method:\n\n🪪 **Aadhaar eKYC** - Quick verification using your Aadhaar number\n📄 **DigiLocker** - Upload documents from your DigiLocker\n\nYou can also upload documents directly for verification.",
        
        "face_verification": "Almost there! Now I need to capture your photo for biometric verification. This helps us ensure account security. Please position your face clearly in the camera frame and click capture. 📸",
        
        "additional_info": "Great! Your identity is verified. Now I need some additional information to complete your profile. This helps us provide better services tailored to your needs. 📋",
        
        "esign": "Final step! Please review your application details and provide your digital signature to complete the account opening process. ✍️",
        
        "completion": "🎉 Congratulations! Your account opening is complete! \n\nYour application has been submitted successfully. You'll receive:\n• Account details via SMS/Email within 24 hours\n• Debit card delivery in 3-5 business days\n• Welcome kit with all account information\n\nThank you for choosing us! - Boardy 😊"
    }
    
    return responses.get(step, "I'm Boardy, and I'm here to help you with your account opening. What would you like to know?")

# Routes
@api_router.post("/onboarding/start")
async def start_onboarding():
    session = OnboardingSession()
    await db.onboarding_sessions.insert_one(session.dict())
    
    # Create initial chat message
    initial_message = ChatMessage(
        session_id=session.id,
        message=get_ai_response("welcome"),
        sender="agent"
    )
    await db.chat_messages.insert_one(initial_message.dict())
    
    return {"session_id": session.id, "message": initial_message.message}

@api_router.get("/onboarding/{session_id}")
async def get_session(session_id: str):
    session = await db.onboarding_sessions.find_one({"id": session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    # Remove the MongoDB _id field from the response
    if "_id" in session:
        del session["_id"]
    return session

@api_router.post("/chat")
async def chat(message: ChatMessage):
    # Store user message
    await db.chat_messages.insert_one(message.dict())
    
    # Get session
    session = await db.onboarding_sessions.find_one({"id": message.session_id})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Generate AI response based on current step
    ai_response = get_ai_response(session["current_step"])
    
    # Store AI response
    ai_message = ChatMessage(
        session_id=message.session_id,
        message=ai_response,
        sender="agent"
    )
    await db.chat_messages.insert_one(ai_message.dict())
    
    return {"message": ai_response}

@api_router.get("/chat/{session_id}")
async def get_chat_history(session_id: str):
    messages = await db.chat_messages.find({"session_id": session_id}).sort("timestamp", 1).to_list(100)
    return messages

@api_router.post("/verify/phone")
async def verify_phone(request: VerificationRequest):
    # Mock phone verification
    await asyncio.sleep(1)  # Simulate API delay
    
    # Update session
    await db.onboarding_sessions.update_one(
        {"id": request.session_id},
        {"$set": {
            "customer_phone": request.phone,
            "current_step": "phone_otp_verification",
            "progress_percentage": 15,
            "updated_at": datetime.utcnow()
        }}
    )
    
    # Create AI response
    ai_message = ChatMessage(
        session_id=request.session_id,
        message=get_ai_response("phone_otp_verification"),
        sender="agent"
    )
    await db.chat_messages.insert_one(ai_message.dict())
    
    return {"success": True, "message": "OTP sent successfully to your mobile", "otp": "123456"}

@api_router.post("/verify/otp")
async def verify_otp(request: VerificationRequest):
    # Mock OTP verification
    await asyncio.sleep(1)
    
    # Check verification type and OTP
    if request.verification_type == "phone":
        if request.otp != "123456":
            return {"success": False, "message": "Invalid OTP. Please try again."}
        
        # Update session for successful phone verification
        await db.onboarding_sessions.update_one(
            {"id": request.session_id},
            {"$set": {
                "current_step": "email_verification",
                "progress_percentage": 25,
                "updated_at": datetime.utcnow()
            }}
        )
        
        ai_message = ChatMessage(
            session_id=request.session_id,
            message=get_ai_response("email_verification"),
            sender="agent"
        )
        await db.chat_messages.insert_one(ai_message.dict())
        
        return {"success": True, "message": "Phone verified successfully!"}
    
    elif request.verification_type == "email":
        if request.otp != "654321":
            return {"success": False, "message": "Invalid email OTP. Please try again."}
        
        # Update session for successful email verification
        await db.onboarding_sessions.update_one(
            {"id": request.session_id},
            {"$set": {
                "current_step": "pan_verification",
                "progress_percentage": 35,
                "updated_at": datetime.utcnow()
            }}
        )
        
        # Send verification success email (mock)
        ai_message = ChatMessage(
            session_id=request.session_id,
            message="Perfect! Email verified successfully! ✅ I've sent a verification confirmation to your email. " + get_ai_response("pan_verification"),
            sender="agent"
        )
        await db.chat_messages.insert_one(ai_message.dict())
        
        return {"success": True, "message": "Email verified successfully! Confirmation sent to your email."}
    
    return {"success": False, "message": "Invalid verification type."}

@api_router.post("/verify/email")
async def verify_email(request: VerificationRequest):
    # Mock email verification - send OTP to email
    await asyncio.sleep(1)
    
    await db.onboarding_sessions.update_one(
        {"id": request.session_id},
        {"$set": {
            "customer_email": request.email,
            "current_step": "email_otp_verification",
            "progress_percentage": 30,
            "updated_at": datetime.utcnow()
        }}
    )
    
    ai_message = ChatMessage(
        session_id=request.session_id,
        message=get_ai_response("email_otp_verification"),
        sender="agent"
    )
    await db.chat_messages.insert_one(ai_message.dict())
    
    return {"success": True, "message": "OTP sent successfully to your email!", "otp": "654321"}

@api_router.post("/kyc/document")
async def verify_kyc_document(request: KYCDocumentRequest):
    # Mock KYC document verification
    await asyncio.sleep(2)  # Simulate processing time
    
    # Handle PAN verification
    if request.document_type == "pan":
        if not request.pan_number or len(request.pan_number) != 10:
            return {"success": False, "message": "Please enter a valid 10-character PAN number."}
        
        # Mock PAN verification
        success = random.choice([True, True, True, False])  # 75% success rate
        
        if not success:
            return {"success": False, "message": "PAN verification failed. Please check your PAN number and try again."}
        
        await db.onboarding_sessions.update_one(
            {"id": request.session_id},
            {"$set": {
                "current_step": "kyc_document",
                "progress_percentage": 45,
                "updated_at": datetime.utcnow()
            }}
        )
        
        ai_message = ChatMessage(
            session_id=request.session_id,
            message=get_ai_response("kyc_document"),
            sender="agent"
        )
        await db.chat_messages.insert_one(ai_message.dict())
        
        return {"success": True, "message": "PAN verified successfully!"}
    
    # Handle Aadhaar/DigiLocker verification
    elif request.document_type in ["aadhaar", "digilocker"]:
        # Simulate random success/failure for demo
        success = random.choice([True, True, True, False])  # 75% success rate
        
        if not success:
            return {"success": False, "message": f"{request.document_type.title()} verification failed. Please check your details and try again."}
        
        await db.onboarding_sessions.update_one(
            {"id": request.session_id},
            {"$set": {
                "current_step": "face_verification",
                "progress_percentage": 60,
                "updated_at": datetime.utcnow()
            }}
        )
        
        ai_message = ChatMessage(
            session_id=request.session_id,
            message=get_ai_response("face_verification"),
            sender="agent"
        )
        await db.chat_messages.insert_one(ai_message.dict())
        
        return {"success": True, "message": f"{request.document_type.title()} verified successfully!"}
    
    return {"success": False, "message": "Invalid document type."}

@api_router.post("/verify/biometric")
async def verify_biometric(request: BiometricRequest):
    # Mock face matching
    await asyncio.sleep(2)
    
    # Simulate biometric matching
    match_score = random.randint(85, 98)
    success = match_score >= 85
    
    if not success:
        return {"success": False, "message": "Face verification failed. Please try again with better lighting."}
    
    await db.onboarding_sessions.update_one(
        {"id": request.session_id},
        {"$set": {
            "current_step": "additional_info",
            "progress_percentage": 80,
            "updated_at": datetime.utcnow()
        }}
    )
    
    ai_message = ChatMessage(
        session_id=request.session_id,
        message=get_ai_response("additional_info"),
        sender="agent"
    )
    await db.chat_messages.insert_one(ai_message.dict())
    
    return {"success": True, "message": f"Face verification successful! Match score: {match_score}%"}

@api_router.post("/submit/additional-info")
async def submit_additional_info(request: AdditionalInfoRequest):
    await asyncio.sleep(1)
    
    await db.onboarding_sessions.update_one(
        {"id": request.session_id},
        {"$set": {
            "current_step": "esign",
            "progress_percentage": 90,
            "updated_at": datetime.utcnow()
        }}
    )
    
    ai_message = ChatMessage(
        session_id=request.session_id,
        message=get_ai_response("esign"),
        sender="agent"
    )
    await db.chat_messages.insert_one(ai_message.dict())
    
    return {"success": True, "message": "Information saved successfully!"}

@api_router.post("/esign")
async def complete_esign(request: ESignRequest):
    await asyncio.sleep(2)
    
    await db.onboarding_sessions.update_one(
        {"id": request.session_id},
        {"$set": {
            "current_step": "completion",
            "progress_percentage": 100,
            "status": "completed",
            "updated_at": datetime.utcnow()
        }}
    )
    
    ai_message = ChatMessage(
        session_id=request.session_id,
        message=get_ai_response("completion"),
        sender="agent"
    )
    await db.chat_messages.insert_one(ai_message.dict())
    
    return {"success": True, "message": "Onboarding completed successfully!"}

# Include the router in the main app
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()