"""
Sample India jobs for testing the ingestion → matching → feed pipeline WITHOUT a
paid Apify token.

`SAMPLE_RAW_ITEMS` are shaped like Google Jobs actor items, so they flow through
the *real* `ApifyJobsScraper.normalise` path —
exercising location geo-lock, salary parsing, skill extraction, and dedup-id
generation just like production. `sample_job_records()` returns the normalised
`JobRecord`s; `JobIngester.ingest_sample()` upserts them via the same code path
as a live scrape.

Use this to light up the match feed and Aarya's job recommendations end-to-end
today; swap in the live Apify scrape once `APIFY_TOKEN` is configured (P09 / S07).
"""

from __future__ import annotations

from hireloop_api.services.apify.jobs_scraper import ApifyJobsScraper, JobRecord

# Realistic, varied India roles. Descriptions embed real skills + an INR LPA
# band so skill extraction and salary parsing have something to bite on.
SAMPLE_RAW_ITEMS: list[dict] = [
    {
        "title": "Senior Backend Engineer",
        "companyName": "Razorpay",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000001",
        "seniorityLevel": "Senior",
        "employmentType": "Full-time",
        "descriptionText": (
            "Build payment APIs at scale with Python, Django and PostgreSQL. "
            "Experience with Redis, Kafka and AWS preferred. Compensation ₹30-45 LPA."
        ),
    },
    {
        "title": "Frontend Engineer",
        "companyName": "Zerodha",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000002",
        "seniorityLevel": "Mid-Senior level",
        "employmentType": "Full-time",
        "descriptionText": (
            "Own trading dashboards in React, TypeScript and Next.js. Strong CSS "
            "and performance skills. ₹18-28 LPA."
        ),
    },
    {
        "title": "Data Scientist",
        "companyName": "Swiggy",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000003",
        "seniorityLevel": "Senior",
        "employmentType": "Full-time",
        "descriptionText": (
            "Work on demand forecasting with Python, machine learning and SQL. "
            "Spark and analytics experience a plus. ₹25-40 LPA."
        ),
    },
    {
        "title": "DevOps Engineer",
        "companyName": "Flipkart",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000004",
        "seniorityLevel": "Mid-Senior level",
        "employmentType": "Full-time",
        "descriptionText": (
            "Run our platform on Kubernetes and AWS with Terraform and CI/CD. "
            "Linux and SRE background. ₹22-35 LPA."
        ),
    },
    {
        "title": "Full Stack Engineer",
        "companyName": "Meesho",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000005",
        "seniorityLevel": "Mid-Senior level",
        "employmentType": "Full-time",
        "descriptionText": (
            "End-to-end features in React, Node.js and MongoDB. Some Python on the "
            "data side. ₹20-32 LPA."
        ),
    },
    {
        "title": "Backend Engineer (Java)",
        "companyName": "Paytm",
        "location": "Noida, Uttar Pradesh, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000006",
        "seniorityLevel": "Mid-Senior level",
        "employmentType": "Full-time",
        "descriptionText": (
            "Core wallet services in Java and Spring Boot with Kafka and MySQL. ₹18-30 LPA."
        ),
    },
    {
        "title": "Machine Learning Engineer",
        "companyName": "Ola",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000007",
        "seniorityLevel": "Senior",
        "employmentType": "Full-time",
        "descriptionText": (
            "Productionise models with Python, PyTorch and TensorFlow. MLOps and "
            "Kubernetes experience valued. ₹28-45 LPA."
        ),
    },
    {
        "title": "Android Engineer",
        "companyName": "PhonePe",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000008",
        "seniorityLevel": "Mid-Senior level",
        "employmentType": "Full-time",
        "descriptionText": (
            "Build the PhonePe app in Kotlin and Android. Strong on app "
            "performance and architecture. ₹20-35 LPA."
        ),
    },
    {
        "title": "Data Engineer",
        "companyName": "Zomato",
        "location": "Gurugram, Haryana, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000009",
        "seniorityLevel": "Senior",
        "employmentType": "Full-time",
        "descriptionText": (
            "Build data pipelines with Spark, Airflow, SQL and Python on AWS. ₹22-38 LPA."
        ),
    },
    {
        "title": "Product Manager",
        "companyName": "CRED",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000010",
        "seniorityLevel": "Senior",
        "employmentType": "Full-time",
        "descriptionText": (
            "Own the rewards product. Strong on product management, agile and "
            "analytics; work closely with engineering. ₹35-55 LPA."
        ),
    },
    {
        "title": "Senior Backend Engineer (Remote)",
        "companyName": "Postman",
        "location": "Remote, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000011",
        "seniorityLevel": "Senior",
        "employmentType": "Full-time",
        "descriptionText": (
            "Fully remote. Build developer tooling with Python, Go and PostgreSQL. "
            "Distributed systems experience. ₹30-50 LPA."
        ),
    },
    {
        "title": "QA Automation Engineer",
        "companyName": "Freshworks",
        "location": "Chennai, Tamil Nadu, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000012",
        "seniorityLevel": "Mid-Senior level",
        "employmentType": "Full-time",
        "descriptionText": ("Own test automation in Python and Selenium with CI/CD. ₹15-25 LPA."),
    },
    {
        "title": "Growth Marketing Manager",
        "companyName": "Dunzo",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000013",
        "seniorityLevel": "Mid-Senior level",
        "employmentType": "Full-time",
        "descriptionText": (
            "Own growth loops across paid social, SEO, content marketing and analytics. "
            "Experience with Google Ads, Meta Ads, Mixpanel and A/B testing. ₹22-35 LPA."
        ),
    },
    {
        "title": "Senior Product Manager",
        "companyName": "Flipkart",
        "location": "Bengaluru, Karnataka, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000014",
        "seniorityLevel": "Senior",
        "employmentType": "Full-time",
        "descriptionText": (
            "Lead a consumer product squad. Strong product management, agile, analytics "
            "and stakeholder management. 6+ years PM experience. ₹40-60 LPA."
        ),
    },
    {
        "title": "AI Engineer",
        "companyName": "Microsoft India",
        "location": "Hyderabad, Telangana, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000015",
        "seniorityLevel": "Senior",
        "employmentType": "Full-time",
        "descriptionText": (
            "Build GenAI features with Python, PyTorch, LLMs and RAG pipelines. "
            "MLOps on Azure and Kubernetes. ₹35-55 LPA."
        ),
    },
    {
        "title": "Content Marketing Lead",
        "companyName": "Zoho",
        "location": "Chennai, Tamil Nadu, India",
        "jobUrl": "https://jobs.google.com/job/gj_sample_3950000016",
        "seniorityLevel": "Mid-Senior level",
        "employmentType": "Full-time",
        "descriptionText": (
            "Lead B2B content strategy, SEO, newsletters and demand gen campaigns. "
            "Strong writing and marketing analytics. ₹18-28 LPA."
        ),
    },
]


def sample_job_records() -> list[JobRecord]:
    """Normalise the sample raw items through the real Google Jobs path."""
    scraper = ApifyJobsScraper(api_token="sample")
    return scraper.normalise_batch(SAMPLE_RAW_ITEMS)
