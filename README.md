# Eco-Friendly Home Renovation Grant Validation  

## Overview  
This project provides an automated solution for validating grant applications for eco-friendly home renovations. The process ensures the accuracy of claims by cross-verifying data from the application form against supporting documents, such as bank statements, invoices, and renovation images. Various **NLP, computer vision, and large language models (LLMs)** are leveraged to achieve this.  

## Workflow  
Applicants submit an application form to request grant funding for home renovation projects aimed at improving energy efficiency. The application form is assumed to be in JSON format and includes the following seven key fields:  

- **Homeowner Name**  
- **Renovation Type** (e.g., solar panels, heat pumps, insulation)  
- **Model** (if applicable)  
- **Contractor Name**  
- **Completion Date**  
- **Cost**  
- **Property Address**  

Supporting documents are provided to verify the applicant's claims using state-of-the-art machine learning models:  

1. **Bank Statement Validation**: AWS **Textract** is used to extract structured tabular data, and **fuzzy matching techniques** ensure the **date**, **cost**, and **contractor name** align with the application form.  
2. **Invoice Verification**: Textract's layout-preserving mode extracts invoice details, and **Meta’s LLaMA-3** (a cutting-edge large language model) verifies key details such as the **business name**, **cost**, and **renovation type**.  
3. **Renovation Image Analysis**: **LLaVA (Large Language and Vision Assistant)**, a multimodal vision-language model, checks whether the submitted image contains the correct renovation type (e.g., solar panels). **Geotag validation** ensures that the image was taken at the registered property location.  

## Assumptions  
- All data (application form and supporting documents) is stored in AWS S3.  
- The system receives the S3 locations of the required files as input.   

## Output  
The solution generates:  

1. **Confidence Scores**: Indicating an average of the scores across all verification criteria, providing a general assessment of how well the applicant's claims match the provided documents.  
2. **Guidance for Assessors**: Highlighting potential mismatches or discrepancies to assist in identifying pain points quickly.  

## Purpose  
The ultimate goal is to streamline the assessor's workload by providing automated insights, reducing manual effort, and expediting the validation process for eco-friendly home renovation grants.  
