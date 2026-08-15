# Modular Backend V77

V77 extracts Assessments/Homework administration, Push Notifications, and Activation Codes from `main.py` into dedicated routers. Activation redemption logic is moved into a service so enrollment activation and code-use validation are reusable without importing the application bootstrap.

The external HTTP contract is intentionally unchanged.
