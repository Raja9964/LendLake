from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Branch:
    code: str
    name: str
    city: str
    state: str
    region: str
    branch_type: str
    opened_on: date
    weight: float


@dataclass(frozen=True)
class Product:
    code: str
    share: float
    median_amount: float
    sigma: float
    min_amount: float
    max_amount: float
    tenures: tuple[int, ...]
    base_rate: float
    max_rate: float
    risk_factor: float


BRANCHES = (
    Branch("BLR01", "Bengaluru Koramangala", "Bengaluru", "Karnataka", "South", "METRO", date(2016, 4, 1), 1.6),
    Branch("BLR02", "Bengaluru Whitefield", "Bengaluru", "Karnataka", "South", "METRO", date(2018, 7, 1), 1.3),
    Branch("CHE01", "Chennai T Nagar", "Chennai", "Tamil Nadu", "South", "METRO", date(2015, 1, 1), 1.4),
    Branch("HYD01", "Hyderabad Banjara Hills", "Hyderabad", "Telangana", "South", "METRO", date(2017, 3, 1), 1.3),
    Branch("COK01", "Kochi Edappally", "Kochi", "Kerala", "South", "URBAN", date(2019, 9, 1), 0.7),
    Branch("MYS01", "Mysuru Vijayanagar", "Mysuru", "Karnataka", "South", "URBAN", date(2024, 5, 1), 0.5),
    Branch("MUM01", "Mumbai Andheri", "Mumbai", "Maharashtra", "West", "METRO", date(2015, 6, 1), 1.7),
    Branch("PNQ01", "Pune Kothrud", "Pune", "Maharashtra", "West", "METRO", date(2016, 11, 1), 1.1),
    Branch("AMD01", "Ahmedabad Navrangpura", "Ahmedabad", "Gujarat", "West", "URBAN", date(2018, 2, 1), 0.9),
    Branch("STV01", "Surat Adajan", "Surat", "Gujarat", "West", "URBAN", date(2020, 1, 1), 0.6),
    Branch("DEL01", "Delhi Rohini", "Delhi", "Delhi", "North", "METRO", date(2015, 4, 1), 1.5),
    Branch("GGN01", "Gurugram Sector 14", "Gurugram", "Haryana", "North", "METRO", date(2017, 8, 1), 1.0),
    Branch("JAI01", "Jaipur Malviya Nagar", "Jaipur", "Rajasthan", "North", "URBAN", date(2019, 4, 1), 0.7),
    Branch("LKO01", "Lucknow Gomti Nagar", "Lucknow", "Uttar Pradesh", "North", "URBAN", date(2024, 11, 1), 0.6),
    Branch("CCU01", "Kolkata Salt Lake", "Kolkata", "West Bengal", "East", "METRO", date(2016, 1, 1), 1.0),
    Branch("BBI01", "Bhubaneswar Saheed Nagar", "Bhubaneswar", "Odisha", "East", "URBAN", date(2021, 6, 1), 0.5),
    Branch("PAT01", "Patna Boring Road", "Patna", "Bihar", "East", "SEMI_URBAN", date(2022, 2, 1), 0.4),
    Branch("GAU01", "Guwahati GS Road", "Guwahati", "Assam", "East", "SEMI_URBAN", date(2025, 3, 1), 0.4),
)

PRODUCTS = (
    Product("HL_STD", 0.22, 4_500_000, 0.45, 1_000_000, 20_000_000, (180, 240, 300), 8.40, 10.50, 0.45),
    Product("HL_AFF", 0.13, 1_500_000, 0.35, 500_000, 3_500_000, (120, 180, 240), 9.50, 12.00, 0.80),
    Product("PL_SAL", 0.47, 300_000, 0.60, 50_000, 2_500_000, (12, 24, 36, 48, 60), 10.50, 18.00, 1.00),
    Product("PL_SE", 0.18, 250_000, 0.55, 50_000, 1_500_000, (12, 24, 36), 13.00, 22.00, 1.60),
)

# Spellings that turn up in source systems for the same city.
CITY_VARIANTS = {
    "Bengaluru": ["Bangalore", "BANGALORE", "bengaluru"],
    "Mumbai": ["Bombay", "MUMBAI"],
    "Gurugram": ["Gurgaon"],
    "Chennai": ["Madras", "chennai"],
    "Kolkata": ["Calcutta"],
    "Mysuru": ["Mysore"],
    "Kochi": ["Cochin"],
    "Delhi": ["New Delhi", "DELHI"],
}

CITY_PINCODES = {
    "Bengaluru": 560001, "Chennai": 600001, "Hyderabad": 500001, "Kochi": 682001,
    "Mysuru": 570001, "Mumbai": 400001, "Pune": 411001, "Ahmedabad": 380001,
    "Surat": 395001, "Delhi": 110001, "Gurugram": 122001, "Jaipur": 302001,
    "Lucknow": 226001, "Kolkata": 700001, "Bhubaneswar": 751001, "Patna": 800001,
    "Guwahati": 781001,
}

MALE_NAMES = (
    "Aarav", "Arjun", "Rohan", "Karthik", "Rahul", "Imran", "Suresh", "Vikram", "Anil",
    "Deepak", "Manoj", "Sanjay", "Joseph", "Harpreet", "Abhishek", "Nikhil", "Farhan", "Ravi",
)
FEMALE_NAMES = (
    "Priya", "Ananya", "Divya", "Kavya", "Sneha", "Pooja", "Fatima", "Ayesha", "Lakshmi",
    "Meera", "Neha", "Shreya", "Anjali", "Deepa", "Nisha", "Simran", "Mary", "Sana",
)
LAST_NAMES = (
    "Sharma", "Verma", "Iyer", "Reddy", "Nair", "Menon", "Patel", "Shah", "Khan", "Das",
    "Banerjee", "Singh", "Gupta", "Rao", "Kulkarni", "Joshi", "Pillai", "D'Souza", "Mehta",
    "Naidu", "Hegde", "Kumar", "Yadav", "Mishra", "Bose", "Fernandes", "Ahmed", "Agarwal",
)
EMAIL_DOMAINS = ("example.com", "example.net", "example.org")
REJECTION_REASONS = ("LOW_CREDIT_SCORE", "INSUFFICIENT_INCOME", "POLICY_DEVIATION", "INCOMPLETE_DOCS")
BOUNCE_REASONS = ("INSUFFICIENT_FUNDS", "INSUFFICIENT_FUNDS", "MANDATE_CANCELLED", "ACCOUNT_FROZEN")
