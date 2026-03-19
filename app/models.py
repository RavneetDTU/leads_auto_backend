from pydantic import BaseModel, Field, field_validator
from typing import Optional, Dict, Any, List
from datetime import datetime
import uuid
from app.timezone_utils import to_sast

# --- Users ---
class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    token: str
    user: Dict[str, Any]

# --- Campaigns ---
class CampaignBase(BaseModel):
    id: str # Meta Campaign ID
    name: str
    status: str # ACTIVE, PAUSED, etc.
    template_name: Optional[str] = None # WATI template to use
    last_fetch_time: Optional[datetime] = None

class CampaignCreate(CampaignBase):
    pass

class Campaign(CampaignBase):
    pass # No extra fields for now, ID is external

# --- Leads ---
class LeadBase(BaseModel):
    meta_lead_id: Optional[str] = None
    name: str = Field(..., description="Full name of the lead")
    phone: str = Field(..., description="Phone number")
    email: Optional[str] = None
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    assigned_to: Optional[str] = None
    status: str = "new"  # new | contacted | follow_up | closed | responded
    
    # Meta specific raw data
    ad_id: Optional[str] = None
    ad_name: Optional[str] = None
    adset_id: Optional[str] = None
    adset_name: Optional[str] = None
    platform: Optional[str] = "facebook" # facebook | instagram
    
    # Branch / Practice fields (from Meta form field_data)
    province: Optional[str] = None
    preferred_practice: Optional[str] = None
    practice_to_visit: Optional[str] = None
    practice_location: Optional[str] = None
    practice_to_attend: Optional[str] = None
    
    template_message_sent: Optional[bool] = False

class LeadCreate(LeadBase):
    pass

class Lead(LeadBase):
    lead_id: str
    created_at: datetime

    @field_validator('created_at', mode='before')
    @classmethod
    def convert_to_sast(cls, v):
        return to_sast(v)

    class Config:
        from_attributes = True


class LeadWithStatus(LeadBase):
    """
    Lead enriched with live WhatsApp activity data.
    Returned by the date and last-30-days endpoints.
    """
    lead_id: str
    created_at: datetime
    # Live WhatsApp status derived from the messages table:
    #   "new"           – no template sent, no messages
    #   "template_sent" – template sent, no incoming reply yet
    #   "unread"        – customer replied, we haven't replied since
    #   "responded"     – our latest OUT message is newer than latest IN
    whatsapp_status: str = "new"
    last_message_time: Optional[datetime] = None  # most recent message timestamp (either direction)

    @field_validator('created_at', mode='before')
    @classmethod
    def convert_created_at(cls, v):
        return to_sast(v)

    @field_validator('last_message_time', mode='before')
    @classmethod
    def convert_last_activity(cls, v):
        return to_sast(v) if v else None

    class Config:
        from_attributes = True


class LeadStats(BaseModel):
    """Summary counts for a set of leads, broken down by whatsapp_status.

    whatsapp_status values:
      \"new\"                   – no messages, our platform hasn't sent template
      \"initial_template_sent\" – our platform sent the template, no customer reply yet
      \"unread\"                – customer replied (IN), no OUT after it
      \"responded\"             – latest OUT >= latest IN; also when other team's OUT
                                 exists with no customer reply (template_message_sent=False)
    """
    total: int = 0
    new: int = 0
    initial_template_sent: int = 0
    unread: int = 0
    responded: int = 0


class LeadsWithStats(BaseModel):
    """Wrapper returned by the daily-leads and last-30-days endpoints."""
    leads: List[LeadWithStatus]
    stats: LeadStats


# --- Activities ---
class ActivityCreate(BaseModel):
    type: str # call | followup | note | status_change
    data: Dict[str, Any]

class Activity(ActivityCreate):
    activity_id: str
    lead_id: str
    user_id: Optional[str]
    created_at: datetime

# --- WhatsApp ---
class WhatsAppTemplateRequest(BaseModel):
    lead_id: str
    template_name: str
    parameters: Optional[List[Dict[str, str]]] = None

class WhatsAppSessionMessageRequest(BaseModel):
    lead_id: str
    message: str

class WhatsAppMessage(BaseModel):
    message_id: str
    lead_id: str
    phone: str
    direction: str # IN | OUT
    message_type: str # template | session
    template_name: Optional[str] = None
    message_text: Optional[str] = None
    wati_message_id: Optional[str] = None
    status: str # sent | delivered | read | failed
    timestamp: datetime

# --- WhatsApp API Request/Response Models ---
class SendTemplateRequest(BaseModel):
    campaign_id: str
    phone: str

class SendSessionMessageRequest(BaseModel):
    phone: str
    message_text: str

class ChatContactResponse(BaseModel):
    lead_id: Optional[str] = None
    name: Optional[str] = None
    phone: str
    last_message_text: Optional[str] = None
    last_message_time: Optional[datetime] = None
    last_message_direction: Optional[str] = None
    unread_count: int = 0

    @field_validator('last_message_time', mode='before')
    @classmethod
    def convert_to_sast(cls, v):
        return to_sast(v)

class ChatMessageResponse(BaseModel):
    message_id: str
    phone: str
    direction: str
    message_type: Optional[str] = None
    template_name: Optional[str] = None
    message_text: Optional[str] = None
    status: Optional[str] = None
    timestamp: datetime

    @field_validator('timestamp', mode='before')
    @classmethod
    def convert_to_sast(cls, v):
        return to_sast(v)


# --- Lead Detail (Branch Info) ---
class LeadDetailUpdate(BaseModel):
    branch_name: Optional[str] = None
    status: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    city: Optional[str] = None

class LeadDetailResponse(BaseModel):
    lead_id: str
    branch_name: Optional[str] = None
    status: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone_number: Optional[str] = None
    city: Optional[str] = None
    updated_at: Optional[datetime] = None

    @field_validator('updated_at', mode='before')
    @classmethod
    def convert_updated_at(cls, v):
        return to_sast(v)

    class Config:
        from_attributes = True


# --- Lead Notes ---
class LeadNoteCreate(BaseModel):
    content: str = Field(..., description="Note content (max 10 notes per lead)")

class LeadNoteUpdate(BaseModel):
    content: str = Field(..., description="Updated note content")

class LeadNoteResponse(BaseModel):
    id: int
    lead_id: str
    note_number: int
    content: str
    updated_at: Optional[datetime] = None

    @field_validator('updated_at', mode='before')
    @classmethod
    def convert_updated_at(cls, v):
        return to_sast(v)

    class Config:
        from_attributes = True


# --- Lead Answers (Yes/No Questions) ---
class LeadAnswersUpdate(BaseModel):
    # Q1: Do you have difficulty in crowded or noisy situations?
    difficulty_crowded: Optional[bool] = None
    # Q2: Do you think that other people mumble or sound muffled?
    mumble_or_muffled: Optional[bool] = None
    # Q3: Do you intently watch people's face when they speak to you?
    watch_face: Optional[bool] = None

class LeadAnswersResponse(BaseModel):
    lead_id: str
    difficulty_crowded: Optional[bool] = None
    mumble_or_muffled: Optional[bool] = None
    watch_face: Optional[bool] = None
    updated_at: Optional[datetime] = None

    @field_validator('updated_at', mode='before')
    @classmethod
    def convert_updated_at(cls, v):
        return to_sast(v)

    class Config:
        from_attributes = True
