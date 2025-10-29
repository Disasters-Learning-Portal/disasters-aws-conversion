"""
AWS Credentials Configuration Template

IMPORTANT:
1. Copy this file to 'aws_credentials.py' in the same directory
2. Replace the placeholder value with your actual external ID
3. NEVER commit aws_credentials.py to git (it's in .gitignore)

The external ID acts as a password for assuming the upload role.
Only share with authorized users who need upload permissions.
"""

# Replace with your actual external ID (like a password)
EXTERNAL_ID = "your-external-id-here"

# Role ARN for uploading (DO NOT MODIFY)
UPLOAD_ROLE_ARN = "arn:aws:iam::515966502221:role/Jupyterhub-Data-Upload"
