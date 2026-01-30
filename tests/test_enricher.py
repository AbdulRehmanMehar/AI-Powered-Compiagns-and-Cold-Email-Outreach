"""Quick test for lead enricher"""
import asyncio
from lead_enricher import LeadEnricher
from database import leads_collection

async def test():
    # Get a lead with a website
    lead = leads_collection.find_one({
        'raw_data.current_employer_website': {'$exists': True, '$ne': None, '$ne': ''}
    })
    
    if not lead:
        print('No leads with websites found')
        return
    
    print(f'Testing with: {lead.get("first_name", "Unknown")} at {lead.get("company")}')
    print(f'Website: {lead.get("raw_data", {}).get("current_employer_website")}')
    
    enricher = LeadEnricher()
    try:
        result = await enricher.enrich_lead(lead)
        print(f'\nEnrichment result:')
        print(f'  Domain: {result.get("domain")}')
        print(f'  Pages crawled: {result.get("pages_crawled")}')
        if result.get('insights'):
            print(f'  Recent news: {result.get("insights", {}).get("recent_news", "N/A")[:100]}')
            print(f'  Tech stack: {result.get("tech_stack", [])}')
            print(f'  Personalization hooks: {result.get("personalization_hooks", [])}')
        if result.get('error'):
            print(f'  Error: {result.get("error")}')
    finally:
        await enricher.close()

if __name__ == "__main__":
    asyncio.run(test())
