from sqlalchemy import Column, String, DateTime, ForeignKey, Boolean, Text, JSON, Index, Date, Integer, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base

class Campaign(Base):
    __tablename__ = "campaigns"

    id = Column(String, primary_key=True, index=True) # Meta Campaign ID
    name = Column(String)
    status = Column(String) # ACTIVE, PAUSED, ARCHIVED
    template_name = Column(String, nullable=True)
    last_fetch_time = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    leads = relationship("Lead", back_populates="campaign")

class Lead(Base):
    __tablename__ = "leads"

    lead_id = Column(String, primary_key=True, index=True) 
    meta_lead_id = Column(String, unique=True, index=True)
    name = Column(String)
    phone = Column(String, index=True)
    email = Column(String, nullable=True)
    
    campaign_id = Column(String, ForeignKey("campaigns.id"))
    campaign_name = Column(String, nullable=True) 
    
    status = Column(String, default="new") 
    
    # Meta specific raw data
    ad_id = Column(String, nullable=True)
    ad_name = Column(String, nullable=True)
    adset_id = Column(String, nullable=True)
    adset_name = Column(String, nullable=True)
    platform = Column(String, default="facebook")
    
    # Branch / Practice fields (from Meta form field_data)
    province = Column(String, nullable=True)
    preferred_practice = Column(String, nullable=True)
    practice_to_visit = Column(String, nullable=True)
    practice_location = Column(String, nullable=True)
    practice_to_attend = Column(String, nullable=True)
    
    template_message_sent = Column(Boolean, default=False)  # True after template msg sent
    
    created_at = Column(DateTime, default=datetime.utcnow)
    created_date = Column(Date, default=datetime.utcnow) # Added for O(1) date lookup
    
    campaign = relationship("Campaign", back_populates="leads")
    messages = relationship("Message", back_populates="lead")
    detail = relationship("LeadDetail", back_populates="lead", uselist=False)
    notes = relationship("LeadNote", back_populates="lead", order_by="LeadNote.note_number")
    answers = relationship("LeadAnswers", back_populates="lead", uselist=False)
    
    __table_args__ = (
        Index('idx_leads_campaign_id_hash', "campaign_id", postgresql_using='hash'),
        Index('idx_leads_created_date_hash', "created_date", postgresql_using='hash'),
    )

class Message(Base):
    __tablename__ = "messages"

    message_id = Column(String, primary_key=True, index=True)
    lead_id = Column(String, ForeignKey("leads.lead_id"), nullable=True) # nullable if lead not found
    phone = Column(String, index=True)
    direction = Column(String) # IN | OUT
    message_type = Column(String)
    template_name = Column(String, nullable=True)  # Template name if template message
    message_text = Column(Text, nullable=True)
    wati_message_id = Column(String, nullable=True, index=True)  # WATI's message ID
    wati_raw_data = Column(JSON, nullable=True)
    status = Column(String, default="received")
    timestamp = Column(DateTime, default=datetime.utcnow)

    lead = relationship("Lead", back_populates="messages")


class LeadDetail(Base):
    """Editable lead detail info — one-to-one with Lead."""
    __tablename__ = "lead_details"

    lead_id = Column(String, ForeignKey("leads.lead_id"), primary_key=True, index=True)
    branch_name = Column(String, nullable=True)
    status = Column(String, nullable=True)        # editable copy
    name = Column(String, nullable=True)           # editable copy
    email = Column(String, nullable=True)          # editable copy
    phone_number = Column(String, nullable=True)   # editable copy
    city = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lead = relationship("Lead", back_populates="detail")


class LeadNote(Base):
    """Notes for a lead (max 10). Each note has a note_number 1-10."""
    __tablename__ = "lead_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(String, ForeignKey("leads.lead_id"), nullable=False, index=True)
    note_number = Column(Integer, nullable=False)  # 1 to 10
    content = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lead = relationship("Lead", back_populates="notes")

    __table_args__ = (
        UniqueConstraint("lead_id", "note_number", name="uq_lead_note"),
    )


class LeadAnswers(Base):
    """Yes/No question answers for a lead — one-to-one with Lead."""
    __tablename__ = "lead_answers"

    lead_id = Column(String, ForeignKey("leads.lead_id"), primary_key=True, index=True)
    # Q1: Do you have difficulty in crowded or noisy situations?
    difficulty_crowded = Column(Boolean, nullable=True)
    # Q2: Do you think that other people mumble or sound muffled?
    mumble_or_muffled = Column(Boolean, nullable=True)
    # Q3: Do you intently watch people's face when they speak to you?
    watch_face = Column(Boolean, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    lead = relationship("Lead", back_populates="answers")
