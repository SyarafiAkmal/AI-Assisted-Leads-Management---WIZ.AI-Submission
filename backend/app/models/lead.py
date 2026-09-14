from sqlalchemy import Boolean, Column, Date, Numeric, String, Text

from app.database import Base


class Lead(Base):
    __tablename__ = "leads"

    record_id = Column(String, primary_key=True)
    name = Column(Text)
    job_title = Column(Text)
    company_name = Column(Text)
    email = Column(Text)
    phone_number = Column(Text)
    country_region = Column(Text)
    city = Column(Text)
    lead_status = Column(Text)
    lifecycle_stage = Column(Text)
    original_source = Column(Text)
    original_source_drill_down_1 = Column(Text)
    contact_owner = Column(Text)
    create_date = Column(Date)
    last_modified_date = Column(Date)
    notes = Column(Text)
    annual_revenue = Column(Numeric)
    marketing_contact_status = Column(Text)
    gdpr_consent = Column(Boolean)
    lead_score = Column(Numeric)