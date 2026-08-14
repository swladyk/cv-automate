# Senior Data Platform Engineer — Meridian Freight (Warsaw, hybrid)

Meridian Freight moves 40 million shipments a year across Central Europe. Our
data platform is how dispatchers, pricing analysts and our customers all find
out where things are. It currently creaks.

We're hiring a senior engineer to own the rebuild.

## What you'd do

- Take our nightly batch ELT — currently a pile of scheduled Bash and cron —
  and turn it into something with lineage, tests and an owner.
- Stand up streaming ingestion for telematics events (~15k/second at peak) so
  the customer-facing tracking page stops being 20 minutes behind reality.
- Set the standards: schema contracts between our services and the warehouse,
  a review process, and enough documentation that the next person can pick it up.
- Mentor two mid-level engineers. We'd like them to be seniors in two years.
- Own the platform budget. It has doubled two years running and nobody can
  explain why.

## What we're looking for

- 5+ years building production data pipelines. You've been on call for one.
- Strong Python and SQL. We're not fussy about frameworks, but we run Airflow
  and dbt and would rather not change that this year.
- Real streaming experience — Kafka, Kinesis or similar. Batch-only candidates
  will struggle with the telematics work.
- Cloud infrastructure as code. We're on AWS, managed with Terraform.
- You can explain a technical trade-off to a dispatcher without condescending.

## Nice to have

- Snowflake (that's our warehouse)
- Kubernetes
- Polish and English both comfortable — the team is bilingual, our customers
  mostly are not.

## The offer

- 22,000–28,000 PLN/month B2B, depending on experience
- Hybrid, 2 days a week in our Wola office
- Actual on-call compensation, not "time off in lieu"

We read every application. If you've done this rebuild before somewhere else,
tell us what you'd do differently this time.
