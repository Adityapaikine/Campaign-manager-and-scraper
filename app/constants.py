from __future__ import annotations

MISSING_VALUE = "-"
DATE_FORMAT = "%d-%b-%Y"

STANDARD_HEADERS: tuple[str, ...] = (
    "Date",
    "Campaign Name",
    "Agent Name",
    "Calling Agent Name",
    "Comment",
    "Dispo",
    "Notes",
    "Email Status",
    "Tenure",
    "First Name",
    "Last Name",
    "Business Email ID",
    "Prospect LinkedIn Link",
    "Job Title",
    "Job Level",
    "Job Function",
    "Company Name",
    "Company Website",
    "Industry",
    "Company Size",
    "See All Company Size",
    "Industry Link",
    "Address",
    "City",
    "State",
    "Zip Code",
    "Address Link",
    "Country",
    "Phone Number",
    "Phone Number Link",
    "Revenue",
    "Revenue Link",
    "SIC Code",
    "NAICS Code",
    "SIC/NAICS Code Link",
    "Audited Date",
    "QA Name",
    "QA Status",
    "Primary Reason",
    "Description",
    "Bounce Email Status",
    "Source File Name",
)

REQUIRED_FIELDS: tuple[str, ...] = (
    "First Name",
    "Last Name",
    "Company Name",
    "Company Website",
)

ROW_STATES: tuple[str, ...] = (
    "Valid", "Valid - Email Generated", "Warning", "Invalid", "Suppressed", "Outside TAL",
    "Duplicate", "Manual Review", "Email Found", "Email Not Found",
)
