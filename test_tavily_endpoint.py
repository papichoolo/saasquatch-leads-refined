"""
Test script for /v1/tavily-enrich endpoint
"""
import requests
import json

BASE_URL = "http://localhost:8000"

def test_tavily_enrich():
    print("=" * 80)
    print("Testing /v1/tavily-enrich endpoint")
    print("=" * 80)
    
    # Test Case: R.R. Interior (no website, no emails, no LinkedIn)
    payload = {
        "name": "R.R. Interior",
        "website": None,
        "location": "Gurugram, Haryana, India",
        "existing_emails": [],
        "existing_linkedin": None,
        "max_queries": 3,
        "fetch_pages": False
    }
    
    print(f"\n📤 Sending request to {BASE_URL}/v1/tavily-enrich")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/v1/tavily-enrich",
            json=payload,
            timeout=30
        )
        
        print(f"\n📥 Response Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("\n✅ Success! Response:")
            print(json.dumps(result, indent=2))
            
            print(f"\n📊 Summary:")
            print(f"  Emails found: {len(result.get('emails', []))}")
            if result.get('emails'):
                for i, email in enumerate(result['emails'][:3], 1):
                    print(f"    {i}. {email}")
            print(f"  LinkedIn: {result.get('linkedin', 'Not found')}")
            print(f"  API calls: {result.get('api_calls_made', 0)}")
            print(f"  Cost: ${result.get('cost_estimate_usd', 0)}")
        else:
            print(f"\n❌ Error Response:")
            print(response.text)
            
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Could not connect to API server.")
        print("Make sure the server is running: python app.py")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")

if __name__ == "__main__":
    test_tavily_enrich()
