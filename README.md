# Funding Application Validation

## Overview  
This project provides an automated solution for validating funding applications and their supporting documents. The process ensures the accuracy of claims by cross-verifying data from the application form against supporting documents, such as bank statements, invoices, and equipment images.

## Workflow  
Applicants submit an application form to request funding for equipment they have purchased. The application form is assumed to be in JSON format and includes the following seven key fields:  
- **Business Name**  
- **Item Name**  
- **Model**  
- **Manufacturer**  
- **Purchase Date**  
- **Cost**  
- **Address**  

Supporting documents are provided to verify the applicant's claims:  
1. **Bank Statement**: Used to confirm the **date**, **cost**, and **business name** match the details on the application form.  
2. **Invoice**: Validates the **business name**, **date**, **cost**, and **equipment details** match the application form.  
3. **Equipment Image**: Verified using embedded geotag data to confirm the **equipment** and **address** provided in the application.  

## Assumptions  
- All data (application form and supporting documents) is stored in AWS S3.  
- The system receives the S3 locations of the required files as input.  

## Output  
The solution generates:  
1. **Confidence Scores**: Indicating the reliability of the matches for each verification point.  
2. **Guidance for Assessors**: Highlighting potential mismatches or discrepancies to assist in identifying pain points quickly.

## Purpose  
The ultimate goal is to streamline the assessor's workload by providing automated insights, reducing manual effort, and expediting the validation process.
