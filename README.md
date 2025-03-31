# Eco-Friendly Home Renovation Grant Validation  

## Overview  
This project provides an automated solution for validating grant applications for eco-friendly home renovations. The process ensures the accuracy of claims by cross-verifying data from the application form against supporting documents, such as bank statements, invoices, and renovation images. Various NLP and computer vision techniques are leveraged to achieve this.  

## Workflow  
Applicants submit an application form to request grant funding for home renovation projects aimed at improving energy efficiency. The application form is assumed to be in JSON format and includes the following seven key fields:  

- **Homeowner Name**  
- **Renovation Type** (e.g., solar panels, heat pumps, insulation)  
- **Model** (if applicable)  
- **Contractor Name**  
- **Completion Date**  
- **Cost**  
- **Property Address**  

Supporting documents are provided to verify the applicant's claims:  

1. **Bank Statement**: Used to confirm the **date**, **cost**, and **contractor name** match the details on the application form.  
2. **Invoice**: Validates the **contractor name**, **date**, **cost**, and **renovation details** match the application form.  
3. **Renovation Image**: Verified to confirm the **installed renovation** and **property location** using embedded geotag data provided in the application.  

## Assumptions  
- All data (application form and supporting documents) is stored in AWS S3.  
- The system receives the S3 locations of the required files as input.  

## Output  
The solution generates:  

1. **Confidence Scores**: Indicating an average of the scores across all verification criteria, providing a general assessment of how well the applicant's claims match the provided documents.  
2. **Guidance for Assessors**: Highlighting potential mismatches or discrepancies to assist in identifying pain points quickly.  

## Purpose  
The ultimate goal is to streamline the assessor's workload by providing automated insights, reducing manual effort, and expediting the validation process for eco-friendly home renovation grants.  
