from google import genai
from google.genai import types
from pydantic import BaseModel, Field
from google.genai.types import GenerateContentConfig, UrlContext, Tool
import json
import time

# Initialize client globally (assuming you have your environment set up)
client = genai.Client()

# Define the Tool (moved outside function for efficiency)
url_context_tool = types.Tool(url_context=types.UrlContext())

class EmailContent(BaseModel):
    rec_email: str = Field(..., description="Recipient's email address")
    subject: str = Field(..., description="Email subject line")
    body: str = Field(..., description="Email body content")

def generate_email(name: str, website: str, rec_email: str) -> EmailContent:
    """
    Generate a professional email using GenAI, grounded by the content of the provided website.
    """
    
    prompt = f"""
Analyze {website} and write a personalized cold email to {name} ({rec_email}).

Format your response exactly as:
Subject: [subject line here]

[email body here]

Include:
- Opening: Reference something specific from their website
- Body (2-3 sentences): Explain how my lead enrichment services can help them
- CTA: Suggest a brief call
- Sign-off: "Best regards, [Your Name]"

Keep it under 150 words total.
"""
    
    try:
        response = client.models.generate_content(
            model="gemini-flash-latest",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[url_context_tool],
                temperature=0.7,
                max_output_tokens=800,
            )
        )
        
        if not response.candidates or response.text is None:
            raise ValueError("Generation failed. Please check the URL and try again.")

        # Parse text response to extract subject and body
        text = response.text.strip()
        
        # Extract subject line
        subject = ""
        body = text
        
        if text.startswith("Subject:"):
            lines = text.split("\n", 1)
            subject = lines[0].replace("Subject:", "").strip()
            body = lines[1].strip() if len(lines) > 1 else ""
        elif "Subject:" in text:
            # Handle case where subject is in the middle
            parts = text.split("Subject:", 1)
            subject_and_rest = parts[1].split("\n", 1)
            subject = subject_and_rest[0].strip()
            body = subject_and_rest[1].strip() if len(subject_and_rest) > 1 else parts[0].strip()
        else:
            # No explicit subject, use first line
            lines = text.split("\n", 1)
            subject = lines[0][:100]  # First 100 chars as subject
            body = text
        
        return EmailContent(
            rec_email=rec_email,
            subject=subject,
            body=body
        )

    except Exception as e:
        # Return a fallback structure on error
        return EmailContent(
            rec_email=rec_email,
            subject="Follow-up",
            body=f"API Call Failed: {str(e)}"
        )

if __name__ == '__main__':
    start_time = time.time()
    
    email = generate_email(
        name="Interior Story", 
        website="http://interiorstory.co.in/",
        rec_email="contact@interiorstory.co.in"
    )

    end_time = time.time()
    print(f"\n[Generated in {end_time - start_time:.2f}s]\n")
    print(f"To: {email.rec_email}")
    print(f"Subject: {email.subject}")
    print(f"\n{email.body}")
    print(f"\n--- JSON ---")
    print(email.model_dump_json(indent=2))
